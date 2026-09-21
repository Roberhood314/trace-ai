export const demoCases = [
  {
    id: "MP-2026-001",
    title: "Người mất tích - hồ sơ thử nghiệm",
    status: "Đang rà soát",
    lastSeen: "42 phút trước",
    radius: "6.8 km",
    confidence: 78,
    priority: "Cao"
  },
  {
    id: "MP-2026-002",
    title: "Hỗ trợ tìm kiếm - hồ sơ mô phỏng",
    status: "Đang xác minh",
    lastSeen: "2 giờ trước",
    radius: "3.2 km",
    confidence: 61,
    priority: "Trung bình"
  }
];

export const demoTimeline = [
  { time: "06:12", label: "Điểm cuối cùng được xác minh", detail: "Nguồn: báo cáo hiện trường" },
  { time: "06:44", label: "Camera hợp lệ ghi nhận hướng di chuyển", detail: "Độ tin cậy 0.82" },
  { time: "07:10", label: "Vùng tìm kiếm được cập nhật", detail: "Zone A mở rộng về hướng Đông Bắc" }
];

export const demoZones = [
  { name: "Zone A", score: 86, radius: "2.1 km", reason: "Dấu vết gần nhất + hướng di chuyển" },
  { name: "Zone B", score: 67, radius: "3.4 km", reason: "Khả năng tiếp cận theo mạng đường" },
  { name: "Zone C", score: 41, radius: "5.8 km", reason: "Vùng dự phòng cần xác minh thêm" }
];
