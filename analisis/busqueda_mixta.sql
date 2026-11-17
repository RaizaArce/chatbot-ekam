-- Busqueda mixta para probar con evaluar_busqueda.py. Parametros: %(v)s vector de la pregunta, %(q)s texto de la pregunta.
-- Une por "rango reciproco" (RRF) tres listas: parecido de significado, palabras en el titulo de la seccion y
-- palabras en el texto; y da una pequena ventaja a los fragmentos del manual que nombra la pregunta.
WITH q AS (
  -- cualquier palabra cuenta (OR); las palabras de relleno de las preguntas no suman
  SELECT replace(plainto_tsquery('spanish', regexp_replace(translate(lower(%(q)s), 'áéíóúü', 'aeiouu'),
           '\m(navasoft|modulo|funciona|como|hago|pantalla|opciones|tiene|registro|nuevo|creo|uno)\M', ' ', 'g'))::text,
           '&', '|')::tsquery AS ts,
         string_to_array(regexp_replace(translate(lower(%(q)s), 'áéíóúü', 'aeiouu'), '[^a-zñ0-9 ]', ' ', 'g'), ' ') AS w
), base AS (
  SELECT id, metadata, embedding <=> %(v)s::vector AS dist,
         to_tsvector('spanish', translate(lower(coalesce(metadata->>'seccion', '')), 'áéíóúü', 'aeiouu')) AS ts_sec,
         to_tsvector('spanish', translate(lower(text), 'áéíóúü', 'aeiouu')) AS ts_txt
  FROM chunks_bge_m3 WHERE metadata->>'pagina' IS NOT NULL
), vector AS (
  SELECT id, row_number() OVER (ORDER BY dist) AS r FROM base ORDER BY dist LIMIT 40
), seccion AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(ts_sec, q.ts, 1) DESC, dist) AS r
  FROM base, q WHERE ts_sec @@ q.ts ORDER BY r LIMIT 40
), texto AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(ts_txt, q.ts, 1) DESC) AS r
  FROM base, q WHERE ts_txt @@ q.ts ORDER BY r LIMIT 40
), manual AS (
  -- cuantas palabras (4+ letras) del nombre del manual aparecen en la pregunta, sin contar las genericas
  SELECT m, count(*) AS n FROM (
    SELECT DISTINCT metadata->>'manual' AS m FROM base) x,
    unnest(string_to_array(regexp_replace(translate(lower(x.m), 'áéíóúü', 'aeiouu'), '[^a-zñ0-9 ]', ' ', 'g'), ' ')) AS p, q
  WHERE length(p) >= 4 AND p NOT IN ('manual', 'guia', 'procedimiento', 'navasoft') AND p = ANY(q.w)
  GROUP BY m
), puntaje AS (
  SELECT b.metadata,
         coalesce(1.0 / (60 + v.r), 0) + %(ps)s * coalesce(1.0 / (60 + s.r), 0) + %(pt)s * coalesce(1.0 / (60 + t.r), 0)
         + %(pm)s * coalesce(m.n, 0) / greatest((SELECT max(n) FROM manual), 1) AS s
  FROM base b LEFT JOIN vector v USING (id) LEFT JOIN seccion s USING (id) LEFT JOIN texto t USING (id)
  LEFT JOIN manual m ON m.m = b.metadata->>'manual'
  WHERE v.id IS NOT NULL OR s.id IS NOT NULL OR t.id IS NOT NULL
)
SELECT metadata->>'archivo', (metadata->>'pagina')::int FROM puntaje ORDER BY s DESC LIMIT 6
