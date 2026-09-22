-- AktivKommuneSchema
--
-- Staging schema that mirrors the shape of a single aktiv-kommune
-- "bookingfrontend" instance (GET /bookingfrontend/searchdataall). One
-- instance can serve several kommuner (interkommunalt samarbeid), so a feed
-- is not assumed to cover exactly one kommune. This intentionally does NOT
-- try to fit the data into the master model (see db/schema_v9.sql) yet --
-- it is the raw landing zone described for the ingest pipeline: land close
-- to source shape first, transform into master tables afterwards.
--
-- Deliberate deviations from a 1:1 mirror (privacy):
--   - buildings.tilsyn_name/_phone/_email and tilsyn_name2/_phone2/_email2
--     (named building-custodian contact) are dropped entirely.
--   - resources.contact_info (free-form contact field, same risk class as
--     tilsyn_*) is dropped entirely.
--   - organizations only keeps id/organization_number/activity_id/
--     show_in_portal/has_org_number. name/phone/email/homepage/co_address/
--     street/zip_code/district/city are dropped: this collection mixes real
--     clubs with private individuals who register to book a venue for a
--     personal event (e.g. activity "Personlig markering"), and those rows
--     carry a real name, personal phone/email and home address. Confirmed
--     against a live sample. Do not add these columns back without Data
--     Privacy Officer sign-off.
--
-- Other source data-quality notes reflected below:
--   - Several "boolean" and "date" fields use sentinel values instead of
--     NULL (e.g. resources.booking_time_default_start/_end use -1 for
--     "unset" and are therefore modeled as INTEGER, not TIME).
--   - resource_categories.parent_id has been observed as 0 (not NULL) for
--     top-level rows, so no FK is enforced on the self-referencing parent_id
--     columns -- clean that up in the transform step, not here.
--   - opening_hours (buildings and resources) is HTML prose written by
--     hand, not structured opening hours -- treat as display text only.
--   - simple_booking_start_date/_end_date are unix epoch seconds (BIGINT),
--     converted to timestamptz in the transform step.
--   - organizations_ids is empty in every row seen so far; if it is ever
--     populated the resource<->organization link belongs in a junction
--     table, not in that column.
--   - the source's "towns" collection (b_id/b_name/id/name) was actually a
--     building-to-bydel relation, not a flat list: normalized below into
--     aktivkommune.bydel (the 9 distinct id/name pairs, under a kommune
--     added for hierarchy even though it's not a source collection) plus
--     aktivkommune.building_districts (the building_id <-> bydel_id
--     relation).

CREATE SCHEMA IF NOT EXISTS aktivkommune;

-- Activities: hierarchical taxonomy of sport/culture/use categories
CREATE TABLE IF NOT EXISTS aktivkommune.activities
(
    id             BIGINT PRIMARY KEY,
    parent_id      BIGINT, -- self-referencing; no FK, see note above
    name           TEXT NOT NULL,
    description    TEXT,
    active         SMALLINT,
    source_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ak_activities_parent
    ON aktivkommune.activities (parent_id);

-- Facilities: amenities that can be attached to a resource (parking, projector, ...)
CREATE TABLE IF NOT EXISTS aktivkommune.facilities
(
    id             BIGINT PRIMARY KEY,
    name           TEXT NOT NULL,
    active         SMALLINT,
    source_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resource categories: hierarchical taxonomy of resource *kind* (room type, court type, ...)
CREATE TABLE IF NOT EXISTS aktivkommune.resource_categories
(
    id             BIGINT PRIMARY KEY,
    name           TEXT NOT NULL,
    active         SMALLINT,
    parent_id      BIGINT, -- self-referencing; no FK, seen as 0 sentinel for "no parent"
    capacity       INTEGER,
    e_lock         SMALLINT,
    source_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ak_resource_categories_parent
    ON aktivkommune.resource_categories (parent_id);

-- Buildings
CREATE TABLE IF NOT EXISTS aktivkommune.buildings
(
    id                     BIGINT PRIMARY KEY,
    activity_id            BIGINT REFERENCES aktivkommune.activities(id),
    deactivate_calendar    SMALLINT,
    deactivate_application SMALLINT,
    deactivate_sendmessage SMALLINT,
    extra_kalendar         SMALLINT,
    name                   TEXT NOT NULL,
    homepage               TEXT,
    location_code          TEXT,
    phone                  TEXT, -- service/department contact, not a named individual
    email                  TEXT, -- service/department contact, not a named individual
    street                 TEXT,
    zip_code               TEXT,
    district               TEXT,
    city                   TEXT,
    calendar_text          TEXT,
    opening_hours          TEXT, -- HTML prose, not structured hours; not machine-parseable
    source_synced_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ak_buildings_activity
    ON aktivkommune.buildings (activity_id);

-- Resources: the actual bookable units (room, court, hall, ...)
CREATE TABLE IF NOT EXISTS aktivkommune.resources
(
    id                            BIGINT PRIMARY KEY,
    name                          TEXT NOT NULL,
    active                        SMALLINT,
    sort                          INTEGER,
    organizations_ids             TEXT, -- format unconfirmed, empty in every sample so far
    json_representation           JSONB,
    rescategory_id                BIGINT REFERENCES aktivkommune.resource_categories(id),
    opening_hours                 TEXT, -- HTML prose, not structured hours; not machine-parseable
    direct_booking                SMALLINT,
    booking_day_default_lenght    INTEGER,
    booking_dow_default_start     INTEGER,
    booking_time_default_start    INTEGER, -- sentinel -1 = unset, not a TIME value
    booking_time_default_end      INTEGER, -- sentinel -1 = unset, not a TIME value
    simple_booking                SMALLINT,
    direct_booking_season_id      BIGINT,
    simple_booking_start_date     BIGINT, -- unix epoch seconds
    booking_month_horizon         INTEGER,
    simple_booking_end_date       BIGINT, -- unix epoch seconds
    booking_day_horizon           INTEGER,
    capacity                      INTEGER,
    deactivate_calendar           SMALLINT,
    deactivate_application        SMALLINT,
    booking_time_minutes          INTEGER,
    booking_limit_number          INTEGER,
    booking_limit_number_horizont INTEGER,
    hidden_in_frontend             SMALLINT,
    activate_prepayment            SMALLINT,
    booking_buffer_deadline        INTEGER,
    description_json                JSONB,
    deny_application_if_booked      SMALLINT,
    short_description                JSONB, -- i18n dict like description_json; empty in every populated row so far
    cancellation_deadline_value      INTEGER,
    cancellation_deadline_unit       TEXT,
    source_synced_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ak_resources_rescategory
    ON aktivkommune.resources (rescategory_id);

-- Building <-> resource (M:N)
CREATE TABLE IF NOT EXISTS aktivkommune.building_resources
(
    building_id BIGINT NOT NULL REFERENCES aktivkommune.buildings(id) ON DELETE CASCADE,
    resource_id BIGINT NOT NULL REFERENCES aktivkommune.resources(id) ON DELETE CASCADE,
    PRIMARY KEY (building_id, resource_id)
);

CREATE INDEX IF NOT EXISTS ix_ak_building_resources_resource
    ON aktivkommune.building_resources (resource_id);

-- Resource <-> activity (M:N)
CREATE TABLE IF NOT EXISTS aktivkommune.resource_activities
(
    resource_id BIGINT NOT NULL REFERENCES aktivkommune.resources(id) ON DELETE CASCADE,
    activity_id BIGINT NOT NULL REFERENCES aktivkommune.activities(id) ON DELETE CASCADE,
    PRIMARY KEY (resource_id, activity_id)
);

CREATE INDEX IF NOT EXISTS ix_ak_resource_activities_activity
    ON aktivkommune.resource_activities (activity_id);

-- Resource <-> facility (M:N)
CREATE TABLE IF NOT EXISTS aktivkommune.resource_facilities
(
    resource_id BIGINT NOT NULL REFERENCES aktivkommune.resources(id) ON DELETE CASCADE,
    facility_id BIGINT NOT NULL REFERENCES aktivkommune.facilities(id) ON DELETE CASCADE,
    PRIMARY KEY (resource_id, facility_id)
);

CREATE INDEX IF NOT EXISTS ix_ak_resource_facilities_facility
    ON aktivkommune.resource_facilities (facility_id);

-- Resource category <-> activity (M:N)
CREATE TABLE IF NOT EXISTS aktivkommune.resource_category_activity
(
    rescategory_id BIGINT NOT NULL REFERENCES aktivkommune.resource_categories(id) ON DELETE CASCADE,
    activity_id    BIGINT NOT NULL REFERENCES aktivkommune.activities(id) ON DELETE CASCADE,
    PRIMARY KEY (rescategory_id, activity_id)
);

CREATE INDEX IF NOT EXISTS ix_ak_resource_category_activity_activity
    ON aktivkommune.resource_category_activity (activity_id);

-- Fagsystem-instans: the aktiv-kommune deployment this staging data was
-- pulled from. Not a source collection -- populated at ingest time, and id
-- is expected to mirror fagsystem_instans.instans_id in the master schema
-- so staging rows can be traced back to a configured instance. One
-- deployment can serve several kommuner (interkommunalt samarbeid), so the
-- kommune link is M:N via fagsystem_instans_kommune, not a column here.
CREATE TABLE IF NOT EXISTS aktivkommune.fagsystem_instans
(
    id       BIGINT PRIMARY KEY,
    name     TEXT NOT NULL,
    base_url TEXT NOT NULL,
    source_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uniq_ak_fagsystem_instans_base_url UNIQUE (base_url)
);

-- Kommune: not a source collection -- the payload has no "kommune" list.
-- Rows here are populated at ingest time from the fagsystem_instans
-- configuration (i.e. which kommuner that instance serves), not from the
-- API response. A single instance can serve several kommuner
-- (interkommunalt samarbeid), so this is a genuine multi-row table rather
-- than one row of context. kommunenr isn't exposed by the endpoint either
-- and comes from the same configuration.
CREATE TABLE IF NOT EXISTS aktivkommune.kommune
(
    id        BIGINT PRIMARY KEY,
    kommunenr CHAR(4),
    name      TEXT NOT NULL,
    source_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- M:N between deployment and kommune: which kommuner a single
-- aktiv-kommune deployment serves. Mirrors fagsystem_instans_kommune in
-- the master schema.
CREATE TABLE IF NOT EXISTS aktivkommune.fagsystem_instans_kommune
(
    instans_id BIGINT NOT NULL REFERENCES aktivkommune.fagsystem_instans(id) ON DELETE CASCADE,
    kommune_id BIGINT NOT NULL REFERENCES aktivkommune.kommune(id) ON DELETE CASCADE,
    PRIMARY KEY (instans_id, kommune_id)
);

CREATE INDEX IF NOT EXISTS ix_ak_fagsystem_instans_kommune_kommune
    ON aktivkommune.fagsystem_instans_kommune (kommune_id);

-- Bydel: the source's own small fixed lookup of districts (9 distinct
-- id<->name pairs observed). Renamed from the source's "towns" label to
-- bydel, which is what the values actually are. Still the *source's own*
-- id, distinct from the authoritative bydel in the master schema --
-- reconcile, don't merge.
CREATE TABLE IF NOT EXISTS aktivkommune.bydel
(
    id         BIGINT PRIMARY KEY,
    kommune_id BIGINT NOT NULL REFERENCES aktivkommune.kommune(id),
    name       TEXT NOT NULL,
    source_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ak_bydel_kommune
    ON aktivkommune.bydel (kommune_id);

-- Building <-> bydel relation.
-- The source's "towns" collection was originally shaped as a flat
-- b_id/b_name/id/name list, but it's actually a building-to-bydel relation,
-- confirmed against a live sample: b_id matches an existing buildings.id
-- 1:1 with zero duplicates, b_name is a 100% redundant copy of that
-- building's name (dropped here), and id/name are exactly the bydel rows
-- above (also matching buildings.district, but with consistent formatting
-- -- the free-text buildings.district field itself is inconsistently
-- cased/suffixed across rows). Normalized here: the name moved into
-- aktivkommune.bydel, this table just holds the relation. 3 of 177
-- buildings had no row here, so the relation is kept optional.
CREATE TABLE IF NOT EXISTS aktivkommune.building_districts
(
    building_id BIGINT PRIMARY KEY REFERENCES aktivkommune.buildings(id) ON DELETE CASCADE,
    bydel_id    BIGINT NOT NULL REFERENCES aktivkommune.bydel(id),
    source_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ak_building_districts_bydel
    ON aktivkommune.building_districts (bydel_id);

-- Organizations: deliberately minimal, see file header. No name/contact/
-- address fields -- this collection mixes real clubs with private
-- individuals booking a venue for a personal event.
CREATE TABLE IF NOT EXISTS aktivkommune.organizations
(
    id                  BIGINT PRIMARY KEY,
    organization_number TEXT,
    has_org_number       BOOLEAN GENERATED ALWAYS AS (organization_number IS NOT NULL AND organization_number <> '') STORED,
    activity_id          BIGINT REFERENCES aktivkommune.activities(id),
    show_in_portal       SMALLINT,
    source_synced_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ak_organizations_activity
    ON aktivkommune.organizations (activity_id);
