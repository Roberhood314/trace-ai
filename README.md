# TRACE-AI

Nền tảng hỗ trợ quản lý vụ việc, người cần tìm, timeline dấu vết, vùng tìm kiếm và phân tích hỗ trợ nghiệp vụ.

## Nguyên tắc
- Không lưu khóa API, mật khẩu hoặc dữ liệu cá nhân thật trong repository.
- Dữ liệu CCCD, thuê bao, IP, vị trí thiết bị, camera nghiệp vụ hoặc dữ liệu nhà mạng chỉ đi qua nguồn được cấp quyền.
- Mọi truy cập dữ liệu nhạy cảm phải có RBAC và audit log.
- AI chỉ hỗ trợ tổng hợp và đề xuất; quyết định nghiệp vụ do người có thẩm quyền thực hiện.

## Chạy local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Mở:
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Docker

```bash
docker compose up --build
```

## Cấu trúc
- `app/main.py`: FastAPI app
- `app/models.py`: dữ liệu vụ việc, người cần tìm, timeline, vùng tìm kiếm, audit
- `app/schemas.py`: request/response schemas
- `app/security.py`: RBAC nền
- `app/services/search_zone.py`: logic chấm điểm vùng tìm kiếm thử nghiệm
