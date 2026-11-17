-- Prueba de navasoft_api dentro de una transaccion que se deshace al final (no deja datos).
BEGIN;
\set QUIET on
SELECT navasoft_api('admin_crear', '{"token":"00000000-0000-0000-0000-000000000000"}') AS "1_sin_sesion";
INSERT INTO usuarios (usuario, nombre, clave_hash, rol, debe_cambiar)
VALUES ('prueba_admin', 'Admin Prueba', crypt('ClaveAdmin123', gen_salt('bf', 10)), 'admin', false);
SELECT navasoft_api('login', '{"usuario":"prueba_admin","clave":"mala"}') AS "2_clave_incorrecta";
CREATE TEMP TABLE t AS SELECT navasoft_api('login', '{"usuario":"PRUEBA_ADMIN","clave":"ClaveAdmin123"}') AS r;
SELECT r - 'token' AS "3_login_ok_mayusculas" FROM t;
SELECT navasoft_api('admin_crear', jsonb_build_object('token', r->>'token', 'usuario', 'Cliente1', 'nombre', 'María Pérez',
       'empresa', 'Empresa Demo', 'clave', 'Inicial2026')) AS "4_admin_crea_cliente" FROM t;
CREATE TEMP TABLE c AS SELECT navasoft_api('login', '{"usuario":"cliente1","clave":"Inicial2026"}') AS r;
SELECT r->'debe_cambiar' AS "5_cliente_debe_cambiar_clave" FROM c;
SELECT navasoft_api('admin_usuarios', jsonb_build_object('token', r->>'token'))->>'error' AS "6_cliente_no_es_admin" FROM c;
SELECT navasoft_api('cambiar_clave', jsonb_build_object('token', r->>'token', 'actual', 'Inicial2026', 'nueva', 'corta')) ->>'error' AS "7_clave_corta" FROM c;
SELECT navasoft_api('cambiar_clave', jsonb_build_object('token', r->>'token', 'actual', 'Inicial2026', 'nueva', 'MiClaveNueva9')) AS "8_cambio_ok" FROM c;
CREATE TEMP TABLE p AS SELECT navasoft_api('nueva_pregunta', jsonb_build_object('token', r->>'token', 'texto', '¿Cómo abro una caja chica?')) AS r FROM c;
SELECT r ? 'conversacion_id' AS "9_conversacion_creada" FROM p;
SELECT navasoft_api('guardar_respuesta', jsonb_build_object('token', c.r->>'token', 'conversacion_id', p.r->>'conversacion_id', 'texto', 'Respuesta de prueba'))->'ok' AS "10_respuesta_guardada" FROM c, p;
SELECT jsonb_array_length(navasoft_api('mensajes', jsonb_build_object('token', c.r->>'token', 'conversacion_id', p.r->>'conversacion_id'))->'mensajes') AS "11_mensajes_en_historial" FROM c, p;
SELECT navasoft_api('mensajes', jsonb_build_object('token', t.r->>'token', 'conversacion_id', p.r->>'conversacion_id'))->>'error' AS "12_otro_usuario_no_ve_chat_ajeno" FROM t, p;
DO $$ BEGIN FOR i IN 1..5 LOOP PERFORM navasoft_api('login', '{"usuario":"cliente1","clave":"x"}'); END LOOP; END $$;
SELECT navasoft_api('login', '{"usuario":"cliente1","clave":"MiClaveNueva9"}')->>'error' AS "13_bloqueo_tras_5_intentos";
SELECT clave_hash LIKE '$2a$%' AS "14_clave_cifrada_bcrypt" FROM usuarios WHERE usuario = 'cliente1';
ROLLBACK;
