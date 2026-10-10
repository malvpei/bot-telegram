# Apps iPhone icon sources

The packaged icons are the real app artwork returned by Apple's public iTunes
Lookup API on 2026-10-08, not generated or redrawn logos. The renderer applies
the normal iOS rounded-square mask when displaying a card.

| File | Official App Store listing | Lookup endpoint |
| --- | --- | --- |
| `notion.png` | https://apps.apple.com/us/app/id1232780281 | https://itunes.apple.com/lookup?id=1232780281&country=us |
| `claude.png` | https://apps.apple.com/us/app/id6473753684 | https://itunes.apple.com/lookup?id=6473753684&country=us |
| `mathway.png` | https://apps.apple.com/us/app/id467329677 | https://itunes.apple.com/lookup?id=467329677&country=us |
| `screenzen.png` | https://apps.apple.com/us/app/id1541027222 | https://itunes.apple.com/lookup?id=1541027222&country=us |
| `fintonic.png` | https://apps.apple.com/es/app/id672220319 | https://itunes.apple.com/lookup?id=672220319&country=es |

ParkEz and Waze reuse the existing real artwork in `cartools/iconos/`. Card
titles, subtitles and buttons intentionally match the user's supplied
screenshots; they are not a live App Store availability or installation status.
