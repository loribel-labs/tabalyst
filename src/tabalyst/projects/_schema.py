# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Explicit project-db schema. Cross-schema FKs are validated by the loader.

DuckDB 1.5.5 cannot express foreign keys between meta and data. Do not move
objects or drop the binding: _validation checks these links on build/reopen.
"""

DUCKDB_VERSION = "1.5.5"
STORAGE_COMPATIBILITY = "v1.4.0"
FORMAT = "tabalyst.project-db"
FORMAT_VERSION = "0.1.0a"
FORMAT_REVISION = LOADER_VERSION = RECORD_SEMANTICS_VERSION = 1

SCHEMA = """
CREATE SCHEMA meta;
CREATE SCHEMA data;
CREATE TABLE meta.format (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    format VARCHAR NOT NULL,
    format_version VARCHAR NOT NULL,
    format_revision INTEGER NOT NULL,
    project_id VARCHAR NOT NULL,
    workspace_id VARCHAR NOT NULL,
    generation_id VARCHAR NOT NULL,
    scan_sha256 VARCHAR NOT NULL,
    duckdb_version VARCHAR NOT NULL,
    storage_compatibility VARCHAR NOT NULL,
    loader_version INTEGER NOT NULL,
    record_semantics_version INTEGER NOT NULL
);
CREATE TABLE meta.datasets (
    dataset_id VARCHAR PRIMARY KEY,
    ordinal BIGINT NOT NULL UNIQUE CHECK (ordinal > 0),
    kind VARCHAR NOT NULL CHECK (kind IN ('table', 'document', 'collection')),
    collection_path_json VARCHAR,
    record_count BIGINT NOT NULL CHECK (record_count >= 0)
);
CREATE TABLE meta.fields (
    dataset_id VARCHAR NOT NULL REFERENCES meta.datasets(dataset_id),
    field_id VARCHAR NOT NULL,
    ordinal BIGINT NOT NULL CHECK (ordinal > 0),
    path_json VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    display VARCHAR NOT NULL,
    parent_field_id VARCHAR,
    collection_dataset_id VARCHAR,
    PRIMARY KEY (dataset_id, field_id),
    UNIQUE (dataset_id, ordinal),
    UNIQUE (dataset_id, path_json)
);
CREATE TABLE data.records (
    dataset_id VARCHAR NOT NULL,
    record_index BIGINT NOT NULL CHECK (record_index > 0),
    location_json VARCHAR NOT NULL,
    depth_truncated BIGINT NOT NULL CHECK (depth_truncated >= 0),
    observation_count BIGINT NOT NULL CHECK (observation_count >= 0),
    with_missing BOOLEAN NOT NULL,
    is_empty BOOLEAN NOT NULL,
    duplicate_key BLOB CHECK (duplicate_key IS NULL OR octet_length(duplicate_key) = 16),
    PRIMARY KEY (dataset_id, record_index)
);
CREATE TABLE data.observations (
    dataset_id VARCHAR NOT NULL,
    record_index BIGINT NOT NULL,
    observation_index BIGINT NOT NULL CHECK (observation_index > 0),
    path_json VARCHAR NOT NULL,
    field_id VARCHAR,
    native_type VARCHAR NOT NULL,
    raw_text VARCHAR,
    array_length BIGINT,
    PRIMARY KEY (dataset_id, record_index, observation_index),
    FOREIGN KEY (dataset_id, record_index)
        REFERENCES data.records(dataset_id, record_index),
    CHECK (
        (native_type IN ('string', 'integer', 'number', 'boolean')
            AND raw_text IS NOT NULL AND array_length IS NULL)
        OR (native_type IN ('null', 'object')
            AND raw_text IS NULL AND array_length IS NULL)
        OR (native_type = 'array' AND raw_text IS NULL AND array_length >= 0
            AND array_length IS NOT NULL)
    )
);
CREATE TABLE meta.listings (
    dataset_id VARCHAR NOT NULL REFERENCES meta.datasets(dataset_id),
    listing_id VARCHAR NOT NULL CHECK
        (listing_id IN ('records.with_missing', 'records.empty', 'records.duplicates')),
    status VARCHAR NOT NULL,
    record_count BIGINT,
    reason VARCHAR,
    semantics_version INTEGER NOT NULL,
    PRIMARY KEY (dataset_id, listing_id),
    CHECK ((status = 'complete' AND record_count >= 0 AND record_count IS NOT NULL
                AND reason IS NULL)
        OR (status = 'disabled' AND record_count IS NULL AND reason IS NOT NULL))
);
CREATE TABLE data.listing_records (
    dataset_id VARCHAR NOT NULL,
    listing_id VARCHAR NOT NULL,
    record_index BIGINT NOT NULL,
    PRIMARY KEY (dataset_id, listing_id, record_index),
    FOREIGN KEY (dataset_id, record_index)
        REFERENCES data.records(dataset_id, record_index)
);
"""

INGESTION = """
CREATE TEMP TABLE ingest_records (
    dataset_id VARCHAR, record_index BIGINT, location_json VARCHAR,
    depth_truncated BIGINT, observation_count BIGINT, with_missing BOOLEAN,
    is_empty BOOLEAN, duplicate_key BLOB
);
CREATE TEMP TABLE ingest_observations (
    dataset_id VARCHAR, record_index BIGINT, observation_index BIGINT,
    path_json VARCHAR, native_type VARCHAR, raw_text VARCHAR, array_length BIGINT
);
"""
