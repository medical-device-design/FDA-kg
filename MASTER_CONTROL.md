# Master control

These graphs (fda-substance-kg, fda-compliance-kg, fda-drug-biologic-kg, fda-food-cosmetic-kg, fda-animal-health-kg, fda-tobacco-kg, fda-drug-event-kg) are governed by the BMEdesign master control, `medical-device-design/bmedesign-kg` (private).

Before any build, upload or schema change, read there:
1. `MASTER_CONTROL.md`
2. `docs/instructions/fda-products.md` (rulings and open items for these graphs)
3. `requests/DECISIONS.md` (what has been decided)

Requests to the master go in `requests/inbox/` (template `requests/TEMPLATE.md`). Gate before any lakeFS upload: `python kgctl check <graph> --path <release folder or sample>` must reach L1 for develop and L2 for main.
