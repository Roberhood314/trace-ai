# TRACE-AI Web / Pi App Studio

Frontend mobile-first dành cho Pi Browser và luồng upload/import vào Pi App Studio.

## Chạy local

```bash
cd web
npm install
npm run dev
```

## Build

```bash
npm run build
```

Output nằm tại `web/dist`.

## Pi SDK

Pi SDK được nạp trong `index.html`. File `src/pi.js` hiện khởi tạo sandbox và đăng nhập scope `username`.

Khi đưa lên production:
- chuyển `sandbox: true` thành `false`;
- xác thực access token ở backend;
- không lưu API key hay secret ở frontend;
- chỉ yêu cầu scope thật sự cần thiết.

## Dữ liệu

Bản frontend hiện dùng dữ liệu mô phỏng để hoàn thiện UX trước. Không có dữ liệu cá nhân thật trong source code.
