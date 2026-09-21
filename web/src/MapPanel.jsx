import React from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

export default function MapPanel() {
  const center = [10.7769, 106.7009];

  return (
    <div className="real-map">
      <MapContainer center={center} zoom={12} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Circle center={center} radius={2100} pathOptions={{ weight: 2 }} />
        <Circle center={center} radius={3400} pathOptions={{ weight: 1, dashArray: "6 6" }} />
        <Marker position={center}>
          <Popup>Điểm cuối cùng được xác minh — dữ liệu demo</Popup>
        </Marker>
      </MapContainer>
      <div className="map-overlay-label">Dữ liệu bản đồ demo • không phải vị trí người dùng</div>
    </div>
  );
}
