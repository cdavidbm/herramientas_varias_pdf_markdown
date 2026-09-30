# Guía de estilo y de formato

> Escríbela sobre la PRÁCTICA y actualízala cuando la práctica cambie: una guía que nadie sigue genera la mitad de los hallazgos de la revisión de estilo.

## 1. Voz y tono

- Académico, neutral, impersonal (se admite el plural de modestia en recapitulaciones).
- **Descriptivo de las tradiciones:** «según X…», «en la lectura de Y…», sin asumirlas como verdad del libro.
- Sin blindaje ni sobreexplicación. Las distinciones de evidencia NO son blindaje: se conservan.
- Evitar las muletillas medidas en el libro de modelo: frases de remate «Es la/Es el…» en serie, «exacto/exactamente», «notable», «en todas las fuentes», «conviene a» (= cuadra con), «precisamente».

## 2. Términos y transliteración

- Sistema: <p. ej., el de Beneito para el árabe: ŷ, j = ḫ, š, ḏ, ṯ, ḥ, ṣ, ḍ, ṭ, ẓ, ʿ, ʾ, vocales largas con macrón; G para la gayn>. En citas literales se respeta la grafía de la fuente.
- Artículo sin asimilar (al-Raḥmān, no ar-Raḥmān), salvo en citas.
- **Una glosa corta por término**, fijada en el apéndice correspondiente; nunca la misma glosa para dos términos.
- Primera mención en el capítulo que lo trata: **en negrita**, con la glosa tras coma. La cursiva se reserva para los términos extranjeros comunes y el uso metalingüístico.

## 3. Formato markdown

- `# Capítulo N · Título` (una línea). Subtítulo de capítulo, si lo hay: línea en cursiva.
- Secciones numeradas: `## 1.`, `### 1.1`, `#### 1.1.1`. **No renumerar una vez redactados los capítulos**: las remisiones dependen de ello.
- Ficha de un término:
  ```
  ### 4.5 <término> (<glosa>) — [D] · C·A
  > <SIG> §N · <SIG> n.º N · <SIG> cap. N
  <prosa: rasgo en cada fuente y rasgo compartido>
  ```
- Notas `[^N]` numeradas por capítulo. Cada capítulo termina con `## Referencias del capítulo`.
- Marcas de evidencia en prosa: **en negrita**, detrás de la cita y antes del punto: «(Autor, año, §N) **[D]**.»
- Comillas « » y luego “ ”; raya para los incisos —así—; cifras sin punto de millar hasta 9999.

## 4. Citas

Véase `03_BIBLIOGRAFIA.md` §3. Toda cita entre comillas debe ser literal y estar verificada contra la fuente local; si no lo es, se parafrasea sin comillas.

## 5. Remisiones internas

«(véase el capítulo 4, §3.3.3)», «(véase el Excurso, §XIV)», «(capítulo 3, nota 4)». Comprobar con `tools/book_integrity.py`.
