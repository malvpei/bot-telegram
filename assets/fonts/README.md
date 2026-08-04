Coloca aquí ficheros `.ttf` para fijar la tipografía del render.

El renderer busca, en este orden:

1. `*Bold*.ttf` o `*Black*.ttf` (cuando necesita una fuente bold) y `*Regular*.ttf` (cuando necesita una regular)
2. Cualquier otro `.ttf` en este directorio
3. Fuentes del sistema (`DejaVuSans-Bold.ttf`, `arialbd.ttf`, `Helvetica`, etc.)
4. La fuente bitmap por defecto de Pillow (escalada — legible pero menos pulida)

Si despliegas en un contenedor sin Arial ni DejaVu, **deja al menos una fuente
bold y una regular en esta carpeta** o el texto saldrá con la bitmap por
defecto y se verá mucho menos pulido.

Sugerencias libres y compatibles:
- Inter (regular + bold) — https://rsms.me/inter/
- Manrope (regular + bold) — https://manropefont.com/
- Roboto (regular + bold) — https://fonts.google.com/specimen/Roboto

## Tipografía de las tarjetas Tipo 4

`advice/` contiene Inter 4.1 en cuatro pesos (Regular, Medium, SemiBold y
Bold). El renderer la carga exclusivamente para las tarjetas de consejos, de
modo que este rediseño no altera las tipografías de los demás tipos de vídeo.
Inter se distribuye bajo la SIL Open Font License incluida en
`advice/LICENSE.txt`.
