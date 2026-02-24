CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS map_sessions (
  id uuid PRIMARY KEY,
  plot_geom geometry,
  buffer_geom geometry,
  bbox4326 geometry,
  metadata jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS map_features (
  id bigserial PRIMARY KEY,
  session_id uuid REFERENCES map_sessions(id) ON DELETE CASCADE,
  layer text NOT NULL,
  geom geometry,
  props jsonb
);

CREATE INDEX IF NOT EXISTS idx_map_sessions_plot_geom ON map_sessions USING gist (plot_geom);
CREATE INDEX IF NOT EXISTS idx_map_sessions_buffer_geom ON map_sessions USING gist (buffer_geom);
CREATE INDEX IF NOT EXISTS idx_map_features_geom ON map_features USING gist (geom);
CREATE INDEX IF NOT EXISTS idx_map_features_session_layer ON map_features (session_id, layer);
