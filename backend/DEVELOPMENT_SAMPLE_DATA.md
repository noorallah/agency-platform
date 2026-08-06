# Development Sample Data Generator

The canonical guide for the ERP dataset is now:

- [`SAMPLE_DATA_GUIDE.md`](./SAMPLE_DATA_GUIDE.md)

Use this script from `backend`:

```powershell
uv run python scripts/generate_sample_data.py --yes
```

Verify seed integrity:

```powershell
uv run python scripts/verify_sample_data.py
```

Reset only:

```powershell
uv run python scripts/generate_sample_data.py reset --yes
```
