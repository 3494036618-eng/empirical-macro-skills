from conftest import FIXTURES, SCHEMAS, load_json
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_CASES = {
    "macro-data-request.schema.json": "request",
    "series-specification.schema.json": "series-specification",
    "provenance.schema.json": "provenance",
    "macro-data-result.schema.json": "result",
    "run-manifest.schema.json": "run-manifest",
}


def test_all_schemas_are_valid_draft_2020_12_documents():
    for schema_file in SCHEMA_CASES:
        schema = load_json(SCHEMAS / schema_file)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        Draft202012Validator.check_schema(schema)


def test_each_schema_accepts_its_positive_example_and_rejects_its_negative_example():
    examples = FIXTURES / "synthetic" / "schema-examples"
    for schema_file, example_prefix in SCHEMA_CASES.items():
        schema = load_json(SCHEMAS / schema_file)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        valid_errors = list(
            validator.iter_errors(load_json(examples / f"{example_prefix}.valid.json"))
        )
        invalid_errors = list(
            validator.iter_errors(load_json(examples / f"{example_prefix}.invalid.json"))
        )

        assert valid_errors == []
        assert invalid_errors != []


def test_result_schema_resolves_provenance_from_a_fresh_standalone_entrypoint():
    schema = load_json(SCHEMAS / "macro-data-result.schema.json")
    instance = load_json(FIXTURES / "synthetic" / "schema-examples" / "result.valid.json")

    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(instance)
