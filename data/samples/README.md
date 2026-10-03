### Sample college: BDG2 site Fox

- **Source:** Building Data Genome Project 2 (BDG2), `data/meters/cleaned/electricity_cleaned.csv` and `data/metadata/metadata.csv`, https://github.com/buds-lab/building-data-genome-project-2
- **Paper:** Miller, C., Kathirgamanathan, A., Picchetti, B. et al. (2020). The Building Data Genome Project 2, energy meter data from the ASHRAE Great Energy Predictor III competition. *Scientific Data* 7, 368. https://doi.org/10.1038/s41597-020-00712-x
- **License:** the repository is licensed CC BY-SA 4.0 (the paper is CC BY 4.0). This sample is an adaptation and is shared under CC BY-SA 4.0.
- **What it is:** hourly electricity (kWh used in each hour, local time) for 8 of the buildings at site "Fox", a university campus in the US/Mountain time zone, 2016-2017. BDG2 anonymises sites and buildings; NEXUS does not try to identify them.
- **Changes made:** picked 8 buildings with at least 97% of hours present (3 teaching labs, 2 dormitories, 1 restaurant, 1 office, 1 fitness centre); reshaped to one row per reading; renamed e.g. `Fox_lodging_Alana` to `Dormitory Alana` (`bdg2_fox_8_buildings_metadata.csv` lists the original ids, floor areas and years built).
- **Limits:** the "cleaned" BDG2 file already has some outliers and zero readings removed by its authors, so fewer unusual hours are expected than in raw data. There is no academic calendar or occupancy for this site, so weekdays count as working days and the Institutional page is not available.
