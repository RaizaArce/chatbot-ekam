-- Portal del Asistente NAVASOFT: usuarios, sesiones, conversaciones y mensajes.
-- Toda la logica pasa por la funcion navasoft_api(accion, datos), que n8n llama con parametros
-- (nunca se arma SQL con texto del usuario). Las contrasenas se guardan cifradas con bcrypt (pgcrypto).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS usuarios (
    id            serial PRIMARY KEY,
    usuario       text UNIQUE NOT NULL,
    nombre        text NOT NULL,
    empresa       text,
    clave_hash    text NOT NULL,
    rol           text NOT NULL DEFAULT 'cliente' CHECK (rol IN ('cliente', 'admin')),
    activo        boolean NOT NULL DEFAULT true,
    debe_cambiar  boolean NOT NULL DEFAULT true,   -- obliga a cambiar la clave inicial
    intentos      int NOT NULL DEFAULT 0,          -- intentos fallidos seguidos
    bloqueado_hasta timestamptz,
    creado        timestamptz NOT NULL DEFAULT now(),
    ultimo_acceso timestamptz
);

CREATE TABLE IF NOT EXISTS sesiones (
    token      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id int NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    expira     timestamptz NOT NULL DEFAULT now() + interval '14 days'
);
ALTER TABLE sesiones ALTER COLUMN expira SET DEFAULT now() + interval '14 days';

CREATE TABLE IF NOT EXISTS conversaciones (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id  int NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    titulo      text NOT NULL,
    creado      timestamptz NOT NULL DEFAULT now(),
    actualizado timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversaciones_usuario ON conversaciones (usuario_id, actualizado DESC);
-- titulo_fijo: false mientras la IA todavia puede mejorar el titulo; true si ya tiene uno bueno o el cliente lo renombro
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS titulo_fijo boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS mensajes (
    id              bigserial PRIMARY KEY,
    conversacion_id uuid NOT NULL REFERENCES conversaciones(id) ON DELETE CASCADE,
    rol             text NOT NULL CHECK (rol IN ('usuario', 'bot')),
    texto           text NOT NULL,
    creado          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mensajes_conversacion ON mensajes (conversacion_id, id);
-- valoracion del cliente sobre una respuesta del asistente: 1 = me sirvio, -1 = no me sirvio
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS valoracion smallint CHECK (valoracion IN (-1, 1));

-- respuestas guardadas para preguntas que se repiten (solo primeras preguntas de un chat, con fuente)
CREATE TABLE IF NOT EXISTS respuestas_cache (
    clave     text PRIMARY KEY,           -- pregunta normalizada (minusculas, sin tildes ni signos)
    respuesta text NOT NULL,
    creado    timestamptz NOT NULL DEFAULT now(),
    usos      int NOT NULL DEFAULT 0
);

-- solicitudes de atencion de una persona de soporte
CREATE TABLE IF NOT EXISTS tickets (
    id              serial PRIMARY KEY,
    usuario_id      int NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    conversacion_id uuid REFERENCES conversaciones(id) ON DELETE SET NULL,
    detalle         text NOT NULL,
    estado          text NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'atendido')),
    creado          timestamptz NOT NULL DEFAULT now(),
    atendido        timestamptz
);


-- pedidos que gastan IA por cuenta, para limitar el abuso (se conservan 24 horas)
CREATE TABLE IF NOT EXISTS uso_ia (
    usuario_id int NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creado     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS uso_ia_usuario ON uso_ia (usuario_id, creado);

-- captura de pantalla que el cliente adjunto a una pregunta, para volver a verla en el chat.
-- Puede mostrar datos de su empresa: se borra sola a los 30 dias (ver 'nueva_pregunta')
CREATE TABLE IF NOT EXISTS capturas_chat (
    mensaje_id bigint PRIMARY KEY REFERENCES mensajes(id) ON DELETE CASCADE,
    imagen     text NOT NULL,             -- data:image/jpeg;base64,... (ya achicada por el navegador)
    creado     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS capturas_chat_creado ON capturas_chat (creado);

-- enlace privado para que la consultora vea el caso (conversacion y capturas); caduca a los 30 dias
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS enlace uuid NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS tickets_enlace ON tickets (enlace);

CREATE OR REPLACE FUNCTION navasoft_api(accion text, datos jsonb) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    u      usuarios%ROWTYPE;
    conv   uuid;
    tok    uuid;
    texto  text;
    clave  text;
    mid    bigint;
    resumen   text;
    preguntas text;
    ultima    text;
BEGIN
    datos := coalesce(datos, '{}'::jsonb);

    -- ---------------------------------------------------------- inicio de sesion
    IF accion = 'login' THEN
        SELECT * INTO u FROM usuarios WHERE lower(usuario) = lower(trim(datos->>'usuario'));
        -- el mismo mensaje y un tiempo parecido en todos los fallos: no se revela si el usuario existe
        IF NOT FOUND THEN
            PERFORM crypt(coalesce(datos->>'clave', ''), gen_salt('bf', 10));
            RETURN jsonb_build_object('ok', false, 'error', 'Usuario o contraseña incorrectos. Si fallaste varias veces, espera unos minutos.');
        END IF;
        IF u.bloqueado_hasta IS NOT NULL AND u.bloqueado_hasta > now() THEN
            PERFORM crypt(coalesce(datos->>'clave', ''), u.clave_hash);
            RETURN jsonb_build_object('ok', false, 'error', 'Usuario o contraseña incorrectos. Si fallaste varias veces, espera unos minutos.');
        END IF;
        IF u.clave_hash <> crypt(coalesce(datos->>'clave', ''), u.clave_hash) THEN
            UPDATE usuarios SET intentos = intentos + 1,
                   bloqueado_hasta = CASE WHEN intentos + 1 >= 5 THEN now() + interval '10 minutes' END
             WHERE id = u.id;
            RETURN jsonb_build_object('ok', false, 'error', 'Usuario o contraseña incorrectos. Si fallaste varias veces, espera unos minutos.');
        END IF;
        IF NOT u.activo THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Tu cuenta está desactivada. Comunícate con soporte de EKAM PERÚ.');
        END IF;
        UPDATE usuarios SET intentos = 0, bloqueado_hasta = NULL, ultimo_acceso = now() WHERE id = u.id;
        DELETE FROM sesiones WHERE expira < now();
        INSERT INTO sesiones (usuario_id) VALUES (u.id) RETURNING token INTO tok;
        RETURN jsonb_build_object('ok', true, 'token', tok, 'nombre', u.nombre, 'empresa', u.empresa,
                                  'rol', u.rol, 'debe_cambiar', u.debe_cambiar);
    END IF;

    -- ---------------------------------------------------------- todo lo demas requiere sesion
    BEGIN
        tok := (datos->>'token')::uuid;
    EXCEPTION WHEN others THEN
        tok := NULL;
    END;
    SELECT us.* INTO u FROM sesiones s JOIN usuarios us ON us.id = s.usuario_id
     WHERE s.token = tok AND s.expira > now() AND us.activo;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Tu sesión expiró. Vuelve a iniciar sesión.', 'sesion', false);
    END IF;

    -- la clave inicial se cambia antes de usar cualquier otra funcion (no basta con que lo pida la pagina)
    IF u.debe_cambiar AND accion NOT IN ('logout', 'yo', 'cambiar_clave') THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Debes cambiar tu contraseña inicial para continuar.', 'debe_cambiar', true);
    END IF;

    -- limite de uso de la IA por cuenta: protege la cuota de Gemini y Groq
    IF accion IN ('nueva_pregunta', 'usar_ia', 'sugerir_soporte') THEN
        DELETE FROM sesiones WHERE expira < now();
        DELETE FROM uso_ia WHERE creado < now() - interval '1 day';
        IF (SELECT count(*) FROM uso_ia x WHERE x.usuario_id = u.id AND x.creado > now() - interval '1 minute') >= 20
           OR (SELECT count(*) FROM uso_ia x WHERE x.usuario_id = u.id) >= 500 THEN
            RETURN jsonb_build_object('ok', false, 'limite', true, 'error', 'Enviaste muchas consultas seguidas. Espera unos minutos e inténtalo de nuevo.');
        END IF;
        INSERT INTO uso_ia (usuario_id) VALUES (u.id);
    END IF;

    IF accion = 'logout' THEN
        DELETE FROM sesiones WHERE token = tok;
        RETURN jsonb_build_object('ok', true);

    -- revisa la sesion y el limite antes de gastar IA en dictado por voz o capturas
    ELSIF accion = 'usar_ia' THEN
        RETURN jsonb_build_object('ok', true);

    ELSIF accion = 'yo' THEN
        RETURN jsonb_build_object('ok', true, 'nombre', u.nombre, 'empresa', u.empresa, 'rol', u.rol,
                                  'debe_cambiar', u.debe_cambiar);

    ELSIF accion = 'cambiar_clave' THEN
        IF u.clave_hash <> crypt(coalesce(datos->>'actual', ''), u.clave_hash) THEN
            RETURN jsonb_build_object('ok', false, 'error', 'La contraseña actual no es correcta.');
        END IF;
        clave := coalesce(datos->>'nueva', '');
        IF length(clave) < 8 THEN
            RETURN jsonb_build_object('ok', false, 'error', 'La nueva contraseña debe tener al menos 8 caracteres.');
        END IF;
        UPDATE usuarios SET clave_hash = crypt(clave, gen_salt('bf', 10)), debe_cambiar = false WHERE id = u.id;
        DELETE FROM sesiones WHERE usuario_id = u.id AND token <> tok;   -- cierra otras sesiones abiertas
        RETURN jsonb_build_object('ok', true);

    -- ---------------------------------------------------------- conversaciones
    ELSIF accion = 'conversaciones' THEN
        RETURN jsonb_build_object('ok', true, 'conversaciones', coalesce((
            SELECT jsonb_agg(jsonb_build_object('id', id, 'titulo', titulo, 'actualizado', actualizado)
                             ORDER BY actualizado DESC)
              FROM conversaciones WHERE usuario_id = u.id), '[]'::jsonb));

    ELSIF accion = 'mensajes' THEN
        SELECT id INTO conv FROM conversaciones WHERE id = (datos->>'conversacion_id')::uuid AND usuario_id = u.id;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Conversación no encontrada.');
        END IF;
        RETURN jsonb_build_object('ok', true, 'mensajes', coalesce((
            SELECT jsonb_agg(jsonb_build_object('id', m.id, 'rol', m.rol, 'texto', m.texto, 'creado', m.creado,
                                                'valoracion', m.valoracion, 'captura', c.imagen) ORDER BY m.id)
              FROM mensajes m LEFT JOIN capturas_chat c ON c.mensaje_id = m.id WHERE m.conversacion_id = conv), '[]'::jsonb));

    ELSIF accion = 'nueva_pregunta' THEN
        texto := trim(coalesce(datos->>'texto', ''));
        IF texto = '' OR length(texto) > 2000 THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Escribe una consulta (máximo 2000 caracteres).');
        END IF;
        IF nullif(datos->>'conversacion_id', '') IS NULL THEN
            INSERT INTO conversaciones (usuario_id, titulo)
            VALUES (u.id, 'Nueva conversación') RETURNING id INTO conv;
        ELSE
            SELECT id INTO conv FROM conversaciones WHERE id = (datos->>'conversacion_id')::uuid AND usuario_id = u.id;
            IF NOT FOUND THEN
                RETURN jsonb_build_object('ok', false, 'error', 'Conversación no encontrada.');
            END IF;
        END IF;
        INSERT INTO mensajes (conversacion_id, rol, texto) VALUES (conv, 'usuario', texto) RETURNING id INTO mid;
        DELETE FROM capturas_chat WHERE creado < now() - interval '30 days';
        -- solo una imagen JPEG ya achicada (1600 px caben de sobra en 1,5 MB)
        IF datos->>'captura' ~ '^data:image/jpeg;base64,[A-Za-z0-9+/=]+$' AND length(datos->>'captura') <= 1500000 THEN
            INSERT INTO capturas_chat (mensaje_id, imagen) VALUES (mid, datos->>'captura');
        END IF;
        UPDATE conversaciones SET actualizado = now() WHERE id = conv;
        RETURN jsonb_build_object('ok', true, 'conversacion_id', conv, 'texto', texto);

    ELSIF accion = 'valorar' THEN
        -- solo sobre respuestas del asistente en conversaciones propias
        SELECT m.id, m.texto INTO mid, texto FROM mensajes m JOIN conversaciones c ON c.id = m.conversacion_id
         WHERE m.id = (datos->>'mensaje_id')::bigint AND m.rol = 'bot' AND c.usuario_id = u.id;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Respuesta no encontrada.');
        END IF;
        UPDATE mensajes SET valoracion = CASE WHEN (datos->>'valor')::int > 0 THEN 1 ELSE -1 END WHERE id = mid;
        -- una respuesta que no sirvio deja de entregarse como respuesta guardada
        IF (datos->>'valor')::int < 0 THEN
            DELETE FROM respuestas_cache WHERE respuesta = texto;
        END IF;
        RETURN jsonb_build_object('ok', true);

    ELSIF accion = 'pedir_soporte' THEN
        texto := trim(coalesce(datos->>'detalle', ''));
        IF texto = '' OR length(texto) > 2000 THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Describe brevemente lo que necesitas (máximo 2000 caracteres).');
        END IF;
        SELECT id INTO conv FROM conversaciones
         WHERE id = nullif(datos->>'conversacion_id', '')::uuid AND usuario_id = u.id;
        INSERT INTO tickets (usuario_id, conversacion_id, detalle) VALUES (u.id, conv, texto) RETURNING id INTO mid;
        -- resumen para WhatsApp: quien pide ayuda, que necesita, que pregunto y que le respondio el asistente
        resumen := 'Hola, soy ' || u.nombre || coalesce(' de ' || u.empresa, '') || E'.\nSolicitud de soporte N.º ' || mid
                   || E'\n\nQué necesito:\n' || left(texto, 500);
        IF conv IS NOT NULL THEN
            -- la descripcion automatica de una captura se cambia por el nombre de la pantalla que se ve
            SELECT string_agg('- ' || left(regexp_replace(split_part(x.texto, '[Captura adjunta]', 1), '\s+', ' ', 'g'), 150)
                       || CASE WHEN x.texto LIKE '%[Captura adjunta]%' THEN ' (adjuntó captura de: '
                            || coalesce(nullif(trim(substring(x.texto from 'Pantalla:\s*([^·\n]{1,80})')), ''), 'una pantalla') || ')' ELSE '' END,
                       E'\n' ORDER BY x.id) INTO preguntas
              FROM (SELECT m.id, m.texto FROM mensajes m WHERE m.conversacion_id = conv AND m.rol = 'usuario' ORDER BY m.id DESC LIMIT 5) x;
            SELECT regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(m.texto,
                     '!\[[^\]]*\]\([^)]+\)', '', 'g'), '\]\([^)]+\)', ']', 'g'), '\[\[sugerencias:[^\]]*\]\]', '', 'g'), '\*\*', '', 'g'), '\s+', ' ', 'g')
              INTO ultima FROM mensajes m WHERE m.conversacion_id = conv AND m.rol = 'bot' ORDER BY m.id DESC LIMIT 1;
            IF preguntas IS NOT NULL THEN
                resumen := resumen || E'\n\nLo que consulté al asistente:\n' || preguntas;
            END IF;
            IF ultima IS NOT NULL THEN
                resumen := resumen || E'\n\nÚltima respuesta del asistente:\n' || left(trim(split_part(ultima, '📄', 1)), 300)
                           || coalesce(E'\n' || substring(ultima from '📄.*$'), '');
            END IF;
        END IF;
        -- capturas del chat (hasta 3, las mas recientes) para que el celular las comparta junto con el resumen
        RETURN jsonb_build_object('ok', true, 'ticket', mid, 'whatsapp', '51940455332', 'resumen', left(resumen, 1700),
          'caso', (SELECT enlace FROM tickets WHERE id = mid),
          'capturas', coalesce((SELECT jsonb_agg(imagen) FROM (SELECT c.imagen FROM capturas_chat c JOIN mensajes m ON m.id = c.mensaje_id
                                 WHERE m.conversacion_id = conv ORDER BY m.id DESC LIMIT 3) x), '[]'::jsonb));

    -- ultimos mensajes del chat, resumidos, para que la IA proponga que escribirle a soporte
    ELSIF accion = 'sugerir_soporte' THEN
        SELECT id INTO conv FROM conversaciones WHERE id = nullif(datos->>'conversacion_id', '')::uuid AND usuario_id = u.id;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Conversación no encontrada.');
        END IF;
        SELECT string_agg(CASE WHEN x.rol = 'usuario' THEN 'Cliente: ' ELSE 'Asistente: ' END
                 || left(regexp_replace(regexp_replace(regexp_replace(x.texto, '!\[[^\]]*\]\([^)]+\)|\]\([^)]+\)|\[\[sugerencias:[^\]]*\]\]|\*\*', '', 'g'),
                                                       '\[Captura adjunta\]', '(adjuntó una captura de pantalla:', 'g'), '\s+', ' ', 'g'), 350),
                 E'\n' ORDER BY x.id) INTO texto
          FROM (SELECT m.id, m.rol, m.texto FROM mensajes m WHERE m.conversacion_id = conv ORDER BY m.id DESC LIMIT 6) x;
        RETURN jsonb_build_object('ok', true, 'contexto', coalesce(texto, ''));

    ELSIF accion = 'renombrar' THEN
        texto := left(trim(coalesce(datos->>'titulo', '')), 80);
        IF texto = '' THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Escribe un nombre para la conversación.');
        END IF;
        UPDATE conversaciones SET titulo = texto, titulo_fijo = true
         WHERE id = (datos->>'conversacion_id')::uuid AND usuario_id = u.id;
        RETURN jsonb_build_object('ok', true);

    ELSIF accion = 'borrar_conversacion' THEN
        DELETE FROM conversaciones WHERE id = (datos->>'conversacion_id')::uuid AND usuario_id = u.id;
        RETURN jsonb_build_object('ok', true);

    -- ---------------------------------------------------------- administracion (solo rol admin)
    ELSIF accion LIKE 'admin_%' AND u.rol <> 'admin' THEN
        RETURN jsonb_build_object('ok', false, 'error', 'No tienes permiso para esta acción.');

    ELSIF accion = 'admin_usuarios' THEN
        RETURN jsonb_build_object('ok', true, 'usuarios', coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                       'id', x.id, 'usuario', x.usuario, 'nombre', x.nombre, 'empresa', x.empresa, 'rol', x.rol,
                       'activo', x.activo, 'debe_cambiar', x.debe_cambiar, 'ultimo_acceso', x.ultimo_acceso,
                       'conversaciones', (SELECT count(*) FROM conversaciones c WHERE c.usuario_id = x.id))
                   ORDER BY x.empresa NULLS LAST, x.nombre)
              FROM usuarios x), '[]'::jsonb));

    ELSIF accion = 'admin_crear' THEN
        IF coalesce(trim(datos->>'usuario'), '') = '' OR coalesce(trim(datos->>'nombre'), '') = '' THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Usuario y nombre son obligatorios.');
        END IF;
        IF length(coalesce(datos->>'clave', '')) < 8 THEN
            RETURN jsonb_build_object('ok', false, 'error', 'La contraseña inicial debe tener al menos 8 caracteres.');
        END IF;
        IF EXISTS (SELECT 1 FROM usuarios WHERE lower(usuario) = lower(trim(datos->>'usuario'))) THEN
            RETURN jsonb_build_object('ok', false, 'error', 'Ese usuario ya existe.');
        END IF;
        INSERT INTO usuarios (usuario, nombre, empresa, clave_hash, rol)
        VALUES (lower(trim(datos->>'usuario')), trim(datos->>'nombre'), nullif(trim(datos->>'empresa'), ''),
                crypt(datos->>'clave', gen_salt('bf', 10)),
                CASE WHEN datos->>'rol' = 'admin' THEN 'admin' ELSE 'cliente' END);
        RETURN jsonb_build_object('ok', true);

    ELSIF accion = 'admin_restablecer' THEN
        IF length(coalesce(datos->>'clave', '')) < 8 THEN
            RETURN jsonb_build_object('ok', false, 'error', 'La contraseña debe tener al menos 8 caracteres.');
        END IF;
        UPDATE usuarios SET clave_hash = crypt(datos->>'clave', gen_salt('bf', 10)), debe_cambiar = true,
               intentos = 0, bloqueado_hasta = NULL
         WHERE id = (datos->>'usuario_id')::int;
        DELETE FROM sesiones WHERE usuario_id = (datos->>'usuario_id')::int;
        RETURN jsonb_build_object('ok', true);

    ELSIF accion = 'admin_activar' THEN
        IF (datos->>'usuario_id')::int = u.id THEN
            RETURN jsonb_build_object('ok', false, 'error', 'No puedes desactivar tu propia cuenta.');
        END IF;
        UPDATE usuarios SET activo = (datos->>'activo')::boolean WHERE id = (datos->>'usuario_id')::int;
        IF NOT (datos->>'activo')::boolean THEN
            DELETE FROM sesiones WHERE usuario_id = (datos->>'usuario_id')::int;
        END IF;
        RETURN jsonb_build_object('ok', true);

    -- borra la cuenta con sus conversaciones, capturas y solicitudes de soporte (ON DELETE CASCADE)
    ELSIF accion = 'admin_eliminar' THEN
        mid := (datos->>'usuario_id')::int;
        IF mid = u.id THEN
            RETURN jsonb_build_object('ok', false, 'error', 'No puedes eliminar tu propia cuenta.');
        END IF;
        IF (SELECT rol FROM usuarios WHERE id = mid) = 'admin'
           AND (SELECT count(*) FROM usuarios WHERE rol = 'admin' AND activo AND id <> mid) = 0 THEN
            RETURN jsonb_build_object('ok', false, 'error', 'No se puede eliminar al único administrador activo.');
        END IF;
        DELETE FROM usuarios WHERE id = mid;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('ok', false, 'error', 'La cuenta ya no existe.');
        END IF;
        RETURN jsonb_build_object('ok', true);

    -- respuestas que no sirvieron (valoracion -1) o en las que el asistente no tuvo informacion,
    -- con la pregunta que las origino: indica que manuales o preguntas frecuentes faltan
    ELSIF accion = 'admin_calidad' THEN
        RETURN jsonb_build_object('ok', true,
          'resumen', (SELECT jsonb_build_object(
                'respuestas', count(*),
                'utiles', count(*) FILTER (WHERE mm.valoracion = 1),
                'no_utiles', count(*) FILTER (WHERE mm.valoracion = -1),
                'sin_informacion', count(*) FILTER (WHERE mm.texto ~* '(no (se encuentra|contienen|cuento|está disponible|detallan|dispongo|encuentro)|lamentablemente|lamento informar|ningún fragmento|ninguno de los)'))
              FROM mensajes mm WHERE mm.rol = 'bot'),
          'pendientes', coalesce((
            SELECT jsonb_agg(x ORDER BY x->>'fecha' DESC) FROM (
              SELECT jsonb_build_object(
                       'fecha', m.creado, 'usuario', us.usuario, 'empresa', us.empresa, 'conversacion_id', c.id,
                       'tipo', CASE WHEN m.valoracion = -1 THEN 'No le sirvió' ELSE 'Sin información' END,
                       'pregunta', (SELECT p.texto FROM mensajes p WHERE p.conversacion_id = m.conversacion_id
                                     AND p.id < m.id AND p.rol = 'usuario' ORDER BY p.id DESC LIMIT 1),
                       'respuesta', left(m.texto, 300)) AS x
                FROM mensajes m JOIN conversaciones c ON c.id = m.conversacion_id JOIN usuarios us ON us.id = c.usuario_id
               WHERE m.rol = 'bot' AND (m.valoracion = -1 OR m.texto ~* '(no (se encuentra|contienen|cuento|está disponible|detallan|dispongo|encuentro)|lamentablemente|lamento informar|ningún fragmento|ninguno de los)')
               ORDER BY m.creado DESC LIMIT 100) t), '[]'::jsonb));

    ELSIF accion = 'admin_tickets' THEN
        RETURN jsonb_build_object('ok', true, 'tickets', coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                       'id', t.id, 'fecha', t.creado, 'estado', t.estado, 'detalle', t.detalle,
                       'usuario', us.usuario, 'nombre', us.nombre, 'empresa', us.empresa,
                       'conversacion_id', t.conversacion_id, 'titulo', c.titulo)
                   ORDER BY (t.estado = 'atendido'), t.creado DESC)
              FROM tickets t JOIN usuarios us ON us.id = t.usuario_id LEFT JOIN conversaciones c ON c.id = t.conversacion_id),
            '[]'::jsonb));

    ELSIF accion = 'admin_ticket_estado' THEN
        UPDATE tickets SET estado = CASE WHEN datos->>'estado' = 'atendido' THEN 'atendido' ELSE 'abierto' END,
               atendido = CASE WHEN datos->>'estado' = 'atendido' THEN now() END
         WHERE id = (datos->>'ticket_id')::int;
        RETURN jsonb_build_object('ok', true);

    -- lectura de una conversacion de cliente, para atender su solicitud de soporte
    ELSIF accion = 'admin_conversacion' THEN
        RETURN jsonb_build_object('ok', true,
          'titulo', (SELECT titulo FROM conversaciones WHERE id = (datos->>'conversacion_id')::uuid),
          'mensajes', coalesce((
            SELECT jsonb_agg(jsonb_build_object('rol', m.rol, 'texto', m.texto, 'creado', m.creado, 'valoracion', m.valoracion,
                                                'captura', c.imagen) ORDER BY m.id)
              FROM mensajes m LEFT JOIN capturas_chat c ON c.mensaje_id = m.id
             WHERE m.conversacion_id = (datos->>'conversacion_id')::uuid), '[]'::jsonb));
    END IF;

    RETURN jsonb_build_object('ok', false, 'error', 'Acción no válida.');
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RETURN jsonb_build_object('ok', false, 'error', 'Datos no válidos.');
END;
$$;

-- Guarda la respuesta del asistente. Solo la llama el flujo de n8n: no es una accion de la API,
-- asi un cliente no puede escribir mensajes como si fueran del asistente.
CREATE OR REPLACE FUNCTION navasoft_guardar_respuesta(conv uuid, respuesta text) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    texto text := coalesce(nullif(trim(respuesta), ''),
                           'Lo siento, en este momento no pude responder. Intenta nuevamente en unos minutos.');
    mid   bigint;
BEGIN
    INSERT INTO mensajes (conversacion_id, rol, texto) VALUES (conv, 'bot', texto) RETURNING id INTO mid;
    UPDATE conversaciones SET actualizado = now() WHERE id = conv;
    RETURN jsonb_build_object('ok', true, 'conversacion_id', conv, 'respuesta', texto, 'mensaje_id', mid);
END;
$$;

-- caso para la consultora de soporte: se abre con el enlace privado del ticket (sin iniciar sesion), hasta 30 dias
CREATE OR REPLACE FUNCTION navasoft_caso(enlace_txt text) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    t   tickets%ROWTYPE;
    usu usuarios%ROWTYPE;
BEGIN
    SELECT * INTO t FROM tickets WHERE enlace::text = lower(trim(coalesce(enlace_txt, ''))) AND creado > now() - interval '30 days';
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false);
    END IF;
    SELECT * INTO usu FROM usuarios WHERE id = t.usuario_id;
    RETURN jsonb_build_object('ok', true, 'ticket', t.id, 'nombre', usu.nombre, 'empresa', usu.empresa, 'detalle', t.detalle,
      'creado', t.creado, 'estado', t.estado,
      'mensajes', coalesce((SELECT jsonb_agg(jsonb_build_object('rol', m.rol, 'texto', m.texto, 'creado', m.creado, 'captura', c.imagen) ORDER BY m.id)
                              FROM mensajes m LEFT JOIN capturas_chat c ON c.mensaje_id = m.id
                             WHERE m.conversacion_id = t.conversacion_id), '[]'::jsonb));
END;
$$;
