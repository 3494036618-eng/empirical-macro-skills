# Third-Party Notices

This engineering candidate uses the following direct dependencies:

| Dependency | Version | License | Use |
|---|---:|---|---|
| jsonschema | 4.26.0 | MIT | Draft 2020-12 contract validation |
| Apache Arrow / pyarrow | 21.0.0 | Apache-2.0 | Parquet export |
| mypy | 1.20.2 | MIT | Development type checking only |
| pytest | 8.4.2 | MIT | Development and test only |
| pytest-cov | 7.1.0 | MIT | Development branch coverage only |
| Ruff | 0.16.3 | MIT | Development linting only |
| types-jsonschema | 4.26.0.20260518 | Apache-2.0 | Development type stubs only |
| hatchling | 1.32.0 | MIT | Build backend only |

Upstream license texts and notices:

- <https://github.com/python-jsonschema/jsonschema/blob/v4.26.0/COPYING>
- <https://github.com/apache/arrow/blob/apache-arrow-21.0.0/LICENSE.txt>
- <https://github.com/python/mypy/blob/v1.20.2/LICENSE>
- <https://github.com/pytest-dev/pytest/blob/8.4.2/LICENSE>
- <https://github.com/pytest-dev/pytest-cov/blob/v7.1.0/LICENSE>
- <https://github.com/astral-sh/ruff/blob/0.16.3/LICENSE>
- <https://github.com/python/typeshed/blob/main/LICENSE>
- <https://github.com/pypa/hatch/blob/hatchling-v1.32.0/LICENSE.txt>

This file does not determine the license of `macro-data` itself. Project
publication and redistribution remain blocked until the project owner chooses a
license and confirms DataPro data-use rights.

World Bank WDI data retrieved by the optional `world_bank` Connector is licensed
under CC BY 4.0 according to the dataset-specific catalog entry:

- <https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators>

Generated WDI bundles record the attribution `World Bank, World Development
Indicators (WDI)`. This notice does not extend that license to other World Bank
datasets or third-party sources.
