import React, { useMemo } from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

export default function MapPanel({ timeline = [], zones = [] }) {
  const geoEvents = timeline.filter(
    (x) => Number.isFinite(x.latitude) && Number.isFinite(x.longitude)
  );

  const center = useMemo(() => {
    const latest = [...geoEvents].sort(
      (a, b) => new Date(b.event_time) - new Date(a.event_time)
    )[0];
    if (latest) return [latest.latitude, latest.longitude];
    if (zones[0]) return [zones[0].center_latitude, zones[0].center_longitude];
    return [10.7769, 106.7009];
  }, [timeline, zones]);

  return (
    <div className="real-map">
      <MapContainer key={center.join(":")} center={center} zoom={12} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {zones.map((zone) => (
          <Circle
            key={zone.id || zone.name}
            center={[zone.center_latitude, zone.center_longitude]}
            radius={zone.radius_m}
            pathOptions={{ weight: zone.priority === "high" ? 3 : 2, dashArray: zone.priority === "low" ? "6 6" : undefined }}
          >
            <Popup>
              <strong>{zone.name}</strong><br />
              Điểm ưu tiên: {zone.score}<br />
              {zone.rationale || "Chưa có giải thích"}
            </Popup>
          </Circle>
        ))}

        {geoEvents.map((event) => (
          <Marker key={event.id} position={[event.latitude, event.longitude]}>
            <Popup>
              <strong>{event.event_type}</strong><br />
              {event.description}<br />
              Độ tin cậy: {event.confidence ?? "—"}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      <div className="map-overlay-label">
        {geoEvents.length || zones.length ? "Dữ liệu vụ việc đã tải" : "Bản đồ demo • chưa có dữ liệu định vị vụ việc"}
      </div>
    </div>
  );
}
