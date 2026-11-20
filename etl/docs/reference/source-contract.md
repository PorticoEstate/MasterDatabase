# Kildekontrakt: hva en normalisert instans må levere

Skriptene ([build](../jobs/build.md) og [sync](../jobs/sync.md)) laster
kodeverkene direkte fra `searchdataall`, uten mapping, og kobler på id. Det
forutsetter at hver instans er normalisert og leverer kodeverkene med masterens
id-er.

| Samling | Felt | Krav |
|---|---|---|
| `resource_categories` (lokaletype), `activities`, `facilities` | `id` | Unik i samlingen, og **den samme id-en på tvers av instanser**: masterens `id` er den delte id-en. Nye konsepter opprettes manuelt i masteren med manuelt satt id (neste ledige tall, aldri gjenbruk) |
| | `name` | Samme navn som masteren har for denne id-en. Navnet er unikt per tabell |
| | `parent_id` | Samme forelder som masteren. `id` i samme samling, eller `null` for en rot. Én forelder, ingen sykluser. `facilities` har ikke dette feltet i dag |
| `resources` | `rescategory_id` | `id` i `resource_categories`, og masteren kjenner den |
| `resource_activities`, `resource_facilities` | `resource_id`, `activity_id`/`facility_id` | Peker på en rad i `resources`, og på en id masteren kjenner |

## Hva skjer ved brudd

Masteren eier vokabularet og hierarkiet, så en instans som viker fra det
påvirker aldri masteren, men loggføres i `synk_avvik` (se
[avvik og kildeuttrekk](avvik-and-extracts.md)). Koblingene eies av kommunen og
følger kilden. Brudd lastes ikke stille:

| Brudd | Avvikstype | Følge |
|---|---|---|
| Manglende eller ugyldig `id`, tomt `name`, id som går igjen | `ugyldig_verdi` | Posten sammenlignes ikke med masteren |
| Samme `id` med annet `name` eller annen `parent_id` enn i masteren | `ugyldig_verdi` | Masteren beholder sitt. Avviket sier hva begge har |
| `id` i kodeverket som masteren ikke har | `manglende_forelder` | Ved synk opprettes den ikke. Ved bygging bare hvis navnet ikke er tatt av en annen id |
| Kobling til en id masteren ikke kjenner (`rescategory_id`, `activity_id`, `facility_id`) | `manglende_forelder` | Koblingen lastes ikke; én avviksrad per id |
| Kobling til en ressurs som ikke finnes i uttrekket | `manglende_forelder` | Raden lastes ikke |

## Åpent: fullstendighet

Kontrakten krever ikke at hele treet er med, men i dag er det ikke det. Målt på
Bergen (2026-11-02) mangler 8 av 102 aktiviteter og 4 av 56 lokaletyper sin
forelder i samlingen, fem aktivitets-id-er brukes av koblinger uten å finnes,
og 389 ressurser og 28 bygg er referert uten å være med i uttrekket. Årsaken er
ikke avklart (filtrering i `searchdataall`, eller et annet endepunkt som gir
alt). Med masteren som eier av vokabularet er det mindre kritisk at hver
instans leverer hele treet, men koblingene må fortsatt peke på id-er som
finnes.

Så lenge instansene ikke er normalisert, simulerer
[demo-normaliseringen](../../dev/demo_normalisering/README.md) kontrakten.
