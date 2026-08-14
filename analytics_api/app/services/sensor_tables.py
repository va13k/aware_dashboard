"""Which physical tables a sensor's rows live in.

The export model maps carry two shapes, and both have to be read the same way by
anything that counts rows rather than serialises them. An Android entry is
``(model, schema)``; an iOS entry is either a model or a tuple of models, because
one sensor can be stored across several tables --- ``esm`` and ``wifi`` are, and
that is precisely why the hourly rollup is keyed by table and why the
sensor-keyed count cache leaves those sensors out entirely.

So a caller asking "how many rows does this sensor hold in this window" has to go
sensor -> tables -> rollup, and this is the first arrow. Kept out of the export
router because the export is no longer the only thing that needs it.
"""


def is_android_entry(entry: object) -> bool:
    """Whether an export entry is Android's ``(model, schema)`` pair.

    Recognised by the schema rather than by length, since an iOS entry is also a
    tuple when its sensor spans several tables.
    """
    return isinstance(entry, tuple) and len(entry) == 2 and hasattr(entry[1], "model_fields")


def models_for(entry: object) -> tuple:
    """Every model behind one export entry, whichever shape it came in."""
    if entry is None:
        return ()
    if is_android_entry(entry):
        return (entry[0],)
    return entry if isinstance(entry, tuple) else (entry,)


def tables_for(export_models: dict, sensor: str) -> list[str]:
    """The tables one sensor reads, or an empty list if it is not a sensor here."""
    return [model.__tablename__ for model in models_for(export_models.get(sensor))]


def tables_by_sensor(export_models: dict) -> dict[str, list[str]]:
    """Every sensor's tables, for turning a per-table total back into sensors."""
    return {sensor: tables_for(export_models, sensor) for sensor in export_models}


def sensor_by_table(export_models: dict) -> dict[str, str]:
    """The reverse: which sensor a table belongs to.

    A rollup total arrives keyed by table, and the dialog asks by sensor. Tables
    a sensor does not claim are simply absent, so a table the export does not
    know about is dropped rather than counted under a guess.
    """
    return {
        table: sensor
        for sensor, tables in tables_by_sensor(export_models).items()
        for table in tables
    }
