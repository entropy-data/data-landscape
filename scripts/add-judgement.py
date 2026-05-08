"""One-shot migration: add `judgement` + `judgementReason` to every standard.

Rings: Foundations, Reach-For, Situational, Watch, Caution.
Inserted right after the `status` field on each entry; existing field order
is preserved otherwise.
"""

import json
from collections import OrderedDict
from pathlib import Path

JUDGEMENTS: dict[str, tuple[str, str]] = {
    # Q1 — Interfaces & Protocols
    "http": ("Foundations", "Universal application transport; nobody decides to use it."),
    "jdbc": ("Foundations", "Every JVM data tool speaks it; default for 25 years."),
    "odbc": ("Foundations", "Cross-language equivalent of JDBC; sits behind every BI tool."),
    "openapi": ("Adopt", "De-facto REST description with tooling for almost every language."),
    "asyncapi": ("Adopt", "The OpenAPI-equivalent for event APIs once you commit to documenting them."),
    "mcp": ("Adopt", "Became the AI tool-integration default in 2024–2025."),
    "adbc": ("Adopt", "Arrow-native DB connectivity; the modern replacement for JDBC/ODBC on analytical workloads."),
    "kafka": ("Adopt", "The streaming backbone; competitors challenge the implementation, not the category."),
    "cloudevents": ("Adopt", "Default event envelope; HTTP/Kafka/AMQP/MQTT bindings all standardised."),
    "graphql": ("Situational", "Right for client-driven aggregation; overkill for plain CRUD."),
    "grpc": ("Situational", "Right for service-to-service binary RPC; wrong for browser clients."),
    "odata": ("Situational", "Pick when you live in the Microsoft BI/Dynamics world."),
    "ftp": ("Situational", "B2B file drops; still common when partners can't speak HTTP APIs."),
    "deltasharing": ("Situational", "Cross-org sharing without copies; well-defined niche."),
    "mqtt": ("Situational", "Excellent in IoT/edge, irrelevant outside it."),
    "amqp": ("Situational", "Pick when you want broker semantics (RabbitMQ-shaped problems)."),
    "a2a": ("Assess", "Agent-to-agent protocol; newer and less proven than MCP."),
    "xmla": ("Caution", "Legacy SOAP-based BI protocol; survives only inside MS Analysis Services."),
    "jms": ("Caution", "Java-only messaging API; maintain if you have it, don't pick it new."),

    # Q2 — Storage & Formats
    "json": ("Foundations", "Universal payload format; not a choice."),
    "csv": ("Foundations", "Universal flat file; ugly but ubiquitous."),
    "parquet": ("Foundations", "De-facto columnar storage; baseline for analytics."),
    "s3": ("Foundations", "The object-storage API everyone implements."),
    "yaml": ("Adopt", "Default surface for config and contract specs."),
    "avro": ("Adopt", "Kafka's binary payload of choice; first-class with Schema Registry."),
    "iceberg": ("Adopt", "Default open table format for new lakes; multi-vendor catalog support and ASF governance."),
    "iceberg-catalog": ("Adopt", "Canonical catalog API for Iceberg; multi-vendor implementations."),
    "schema-registry": ("Adopt", "The default Kafka schema-management surface."),
    "arrow": ("Adopt", "In-memory columnar standard powering Flight, ADBC, DataFusion, Polars."),
    "orc": ("Situational", "Pick if you're in Hive/Tez territory; otherwise Parquet wins."),
    "delta": ("Situational", "Reach-For if you're on Databricks; Situational elsewhere."),
    "unity-catalog": ("Situational", "LF-open-sourced but still Databricks-tilted in practice."),
    "xml": ("Assess", "Load-bearing in finance/healthcare/government; not for new payloads."),
    "lance": ("Assess", "AI/ML-optimised columnar format; trajectory good, adoption concentrated."),
    "hudi": ("Assess", "Third-place table format; legitimate CDC-upsert use cases but lost the default slot."),
    "ducklake": ("Assess", "DuckDB-Labs catalog; v1.0 production-ready, ecosystem still small."),
    "dataframe": ("Assess", "Portable Python DataFrame spec; standard exists, adoption uneven."),
    "hdfs": ("Caution", "Hadoop-era distributed FS; object storage replaced it for nearly all new builds."),
    "hive-metastore": ("Caution", "The catalog Iceberg REST is displacing; maintain only."),

    # Q3 — Modeling & Semantics
    "json-schema": ("Adopt", "Default API-payload validation; behind OpenAPI/AsyncAPI."),
    "sql-ddl": ("Adopt", "Universal way to describe a relational schema; portable across engines."),
    "avro-schema": ("Adopt", "Schema language for Kafka payloads; pairs with Schema Registry."),
    "protobuf": ("Adopt", "Strong schema-evolution rules; default for gRPC."),
    "odcs": ("Adopt", "Winning data-contract spec; YAML, multi-vendor."),
    "odps": ("Adopt", "Winning data-product spec; ODCS-aligned."),
    "rdf-owl": ("Situational", "Semantic-web foundation; right when reasoning/inference matter."),
    "dcat": ("Situational", "Mandatory in EU open-data and many regulatory contexts."),
    "skos": ("Situational", "Right when you actually have a taxonomy."),
    "shacl": ("Situational", "Validate RDF; only when you already speak RDF."),
    "json-ld": ("Situational", "Pragmatic semantic-web on-ramp inside ordinary JSON."),
    "xml-schema": ("Assess", "Load-bearing in enterprise integration but not chosen for new work."),
    "linkml": ("Assess", "Multi-output schema language; strong in biomedical, niche elsewhere."),
    "frictionless-table-schema": ("Assess", "Lightweight Frictionless tabular spec; small ecosystem."),
    "shex": ("Assess", "RDF shape validation parallel to SHACL; smaller community."),
    "schemaorg": ("Assess", "Web SEO/structured-data vocabulary; different audience from data-platform work."),
    "osi": ("Assess", "Emerging vendor-neutral semantic exchange; promising, adoption early."),
    "dpds": ("Assess", "Coexists with ODPS but with smaller community."),
    "odpspec": ("Assess", "LF-governed data-product spec; strong on commercial terms, modest adoption."),
    "dprod": ("Assess", "RDF/OWL data-product vocabulary; right only when your stack already lives in linked data."),

    # Q4 — Processing & Operations
    "sql": ("Foundations", "The universal data query language; not a decision."),
    "pandas": ("Foundations", "Universal Python DataFrame; you don't choose it, you encounter it."),
    "spark": ("Adopt", "Default distributed batch+streaming engine."),
    "sql-dml": ("Adopt", "Portable transformation language across relational/lakehouse engines."),
    "dbt": ("Adopt", "Analytics-engineering default: SQL-first models, tests, lineage."),
    "opentelemetry": ("Adopt", "Vendor-neutral observability standard."),
    "openlineage": ("Adopt", "The lineage-emission standard, with column-level support."),
    "opa": ("Adopt", "General-purpose policy engine; mature Rego ecosystem."),
    "sparql": ("Situational", "Query RDF; right when your data lives in triples."),
    "beam": ("Situational", "Write once, run on Flink/Spark/Dataflow; right when runner portability matters."),
    "great-expectations": ("Situational", "Python-first DQ; powerful but heavy."),
    "sodacl": ("Situational", "YAML-first DQ; lighter than Great Expectations, smaller ecosystem."),
    "substrait": ("Assess", "Query-plan IR engines exchange; promising substrate, end users rarely touch it."),
    "gql": ("Assess", "ISO property-graph query language; ratified 2024, adoption nascent."),
    "ibis": ("Assess", "Portable Python DataFrame compiling to many backends; trajectory strong, footprint small."),
    "oors": ("Assess", "BITOL observability/quality-result standard; new and under-adopted."),
    "prov": ("Assess", "W3C provenance vocabulary; predates OpenLineage by a decade, fading."),
    "odrl": ("Assess", "Rights-expression language; relevant where data licensing matters."),
    "mdx": ("Caution", "Multidimensional query language; surviving only in MS Analysis Services."),
    "xslt": ("Caution", "XML transformation; maintain if you have it, don't pick it new."),
}

PATH = Path(__file__).resolve().parent.parent / "standards.json"

def main() -> None:
    with PATH.open(encoding="utf-8") as f:
        data: "OrderedDict[str, OrderedDict]" = json.load(f, object_pairs_hook=OrderedDict)

    expected = set(data.keys())
    given = set(JUDGEMENTS.keys())
    if expected != given:
        missing_in_input = sorted(expected - given)
        unknown_in_input = sorted(given - expected)
        if missing_in_input:
            print(f"  missing judgements for: {missing_in_input}")
        if unknown_in_input:
            print(f"  unknown slugs in input: {unknown_in_input}")
        raise SystemExit(1)

    for slug, (judgement, reason) in JUDGEMENTS.items():
        entry = data[slug]
        new_entry: OrderedDict = OrderedDict()
        inserted = False
        for k, v in entry.items():
            if k in ("judgement", "judgementReason"):
                continue
            new_entry[k] = v
            if k == "status" and not inserted:
                new_entry["judgement"] = judgement
                new_entry["judgementReason"] = reason
                inserted = True
        if not inserted:
            new_entry["judgement"] = judgement
            new_entry["judgementReason"] = reason
        data[slug] = new_entry

    with PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    counts: dict[str, int] = {}
    for j, _ in JUDGEMENTS.values():
        counts[j] = counts.get(j, 0) + 1
    print(f"  wrote {len(data)} entries")
    for ring in ("Foundations", "Adopt", "Situational", "Assess", "Caution"):
        print(f"    {ring}: {counts.get(ring, 0)}")


if __name__ == "__main__":
    main()
