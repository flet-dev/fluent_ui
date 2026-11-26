# Icon fonts

`FluentIcons.ttf` and `SegoeIcons.ttf` contain only the glyphs that fluent_ui's
widgets use. The glyphs come from Microsoft's MIT-licensed
[Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons)
(see [LICENSE](LICENSE)), placed at the codepoints of the `FluentIcons` and
`WindowsIcons` constants the widgets use, and sized to match the glyphs they
replace.

The original fonts, Fabric MDL2 Assets and Segoe Fluent Icons, are not
redistributable, so they aren't bundled. `FluentIcons` and `WindowsIcons`
constants that the widgets don't use have no glyph and draw nothing.

To rebuild the fonts, for example after a widget starts using another icon, run
from the repository root:

```
uvx --with fonttools python tool/build_mit_icon_fonts.py
```

The script finds the glyphs the widgets use, and fails if one has no Fluent UI
System Icons equivalent in its `MAPPING` table.
