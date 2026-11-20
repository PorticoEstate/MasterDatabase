# Avvik og kildeuttrekk

Gjelder alle jobbene ([build](../jobs/build.md), [sync](../jobs/sync.md),
[geocode](../jobs/geocode.md), [gater](../jobs/gater.md)).

## Prinsipp

Hver kjøring registrerer et `kildeuttrekk` (kilde, endepunkt, tidspunkt,
HTTP-status - ikke hele svaret fra kilden). Alt som ikke lar seg laste
loggføres i `synk_avvik` sammen med selve posten som feilet (`rapost`, renset
for personopplysninger som `organizations` og andre persondatafelt): ugyldige
verdier, koblinger til noe som ikke finnes i uttrekket, brudd på kildekontrakten
([source-contract](source-contract.md)), databasefeil og feilet henting. En
enkelt dårlig post stopper aldri hele lasten.

## Gå gjennom avvikene fra siste kjøring

```bash
docker exec portico_masterdb psql -U postgres -d masterdb -c "
    SELECT d.avvik_id, d.kilde, d.avvikstype, d.felt, d.detalj, d.post
    FROM v_synk_avvik_gjeldende g JOIN v_synk_avvik_detalj d ON d.avvik_id = g.id
    WHERE g.avvikstype <> 'manglende_forelder';"
```

`post` er selve posten fra kilden som feilet, lagret direkte på avviket.

## Opprydding

De to nyeste uttrekkene per kilde beholdes, uforbeholdent - bevis for et avvik
ligger på avviket selv, ikke i uttrekket, så gammel metadata kan ryddes trygt
bort. Daemonen sletter dessuten `synk_avvik`-rader eldre enn
`AVVIK_RETENTION_DAYS` (standard 30) i `prune`-jobben, se [daemon](../jobs/daemon.md).
