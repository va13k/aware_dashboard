# Maintenance

Operations a running deployment needs now and then, each run by hand rather than by
setup. Nothing here is part of deploying a study or of collecting from it.

---

## Reclaiming sensor label space

The ten physical sensor tables are created without a `label` column. The client
fills that column from an Android broadcast a study never sends, so on a database
created before it was dropped it holds one empty string per row across the
highest-volume tables. `db/reclaim-sensor-label.sql` removes it there:

```bash
docker exec -i aware_mysql mysql -uroot -p<root-password> aware_android < db/reclaim-sensor-label.sql
```

The script reports each table it touches and can be re-run: a table already
matching the schema is left alone. `bluetooth`, `locations` and `wifi` keep their
`label`, which the client writes.
