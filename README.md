# BTL-KHDV — Hệ thống xếp lịch phòng thi và phòng máy học phần

Bài tập lớn môn Khoa học Dịch vụ. Hệ thống dùng mô hình quy hoạch nguyên tuyến tính (ILP), giải bằng Google OR-Tools CP-SAT, để tự động xếp:

- Lịch thi cuối kỳ: môn nào thi ca nào, ở phòng nào, giám thị nào coi (bài toán A);
- Lịch phòng học / phòng máy thực hành theo tuần (bài toán B, đang làm).

## Tài liệu

Đọc theo thứ tự trước khi viết code:

| Tài liệu | Nội dung |
|---|---|
| [docs/scope.md](docs/scope.md) | Phạm vi đề tài, giả định, ràng buộc, KPI |
| [docs/model_spec.md](docs/model_spec.md) | Đặc tả mô hình toán (bài toán A; bài toán B sẽ bổ sung) |
| [docs/data_schema.md](docs/data_schema.md) | Định dạng dữ liệu đầu vào, cấu hình và file kết quả |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Quy ước làm việc nhóm: nhánh, commit, Pull Request |

## Cài đặt

Cần Python 3.11 trở lên, khuyến nghị 3.12, bản chính thức tải từ python.org.

Trên Windows, dùng lệnh `py -3.12` thay vì `python`. Lý do: nếu máy có cài MSYS2 hoặc Git for Windows bản đầy đủ, lệnh `python` có thể trỏ tới bản Python của MSYS2, và bản này không cài được OR-Tools. Kiểm tra bằng `python -c "import sys; print(sys.executable)"`: nếu đường dẫn chứa `msys64` thì không dùng được.

```powershell
git clone https://github.com/Phamminh161005/BTL-KHDV.git
cd BTL-KHDV
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

Trên macOS hoặc Linux thay hai dòng giữa bằng `python3 -m venv .venv` và `source .venv/bin/activate`.

Cài đặt thành công khi `pytest` báo toàn bộ passed. Hai ca kiểm thử solver sẽ ở trạng thái skipped cho đến khi solver được cài đặt.

Các lệnh bên dưới đều chạy trong môi trường `.venv` đã kích hoạt, từ thư mục gốc của repo.

## Chạy

```powershell
# Xếp lịch thi cho một bộ dữ liệu, ghi kết quả vào output/<tên bộ dữ liệu>/schedule.json
python -m src.run --data data/toy

# Mở giao diện xem lịch
streamlit run app/app.py

# Chạy kiểm thử
pytest
```

## Cấu trúc thư mục

```
├── docs/                  Tài liệu: phạm vi, mô hình, định dạng dữ liệu
├── configs/default.json   Cấu hình mặc định (data_schema mục 6)
├── data/toy/              Bộ dữ liệu nhỏ dùng để kiểm thử (xem data/toy/README.md)
├── output/toy/            Kết quả tham chiếu schedule.json của bộ toy
├── src/
│   ├── instance.py        Cấu trúc dữ liệu dùng chung, giao diện SolveResult của solver
│   ├── config.py          Đọc cấu hình
│   ├── data_loader.py     Đọc và kiểm tra dữ liệu (mã D, P)
│   ├── exam_solver.py     Solver bài toán A
│   ├── room_solver.py     Solver bài toán B
│   ├── schedule.py        Hậu xử lý, dựng schedule.json
│   ├── validator.py       Kiểm tra lời giải độc lập với solver
│   ├── kpi.py             Tính KPI và tính lại điểm phạt
│   ├── generator.py       Sinh dữ liệu giả lập
│   └── run.py             Chạy toàn bộ quy trình
├── app/app.py             Giao diện Streamlit
├── tests/                 Kiểm thử (pytest)
├── experiments/           Script và kết quả thực nghiệm
└── report/                Báo cáo
```

## Trạng thái các thành phần

| Thành phần | Trạng thái |
|---|---|
| `data_loader.py`, `config.py`, `instance.py` | Hoàn chỉnh, có kiểm thử |
| `validator.py`, `kpi.py`, `schedule.py`, `run.py` | Hoàn chỉnh, có kiểm thử |
| `generator.py` | Hoàn chỉnh, có kiểm thử; dữ liệu sinh sẵn (seed 1) trong `data/toy_gen`, `data/medium`, `data/large` |
| `exam_solver.py` | Chưa cài đặt (Khỏe) |
| `room_solver.py` | Chờ spec bài toán B (Minh viết spec, Khỏe cài đặt) |
| `app/app.py` | Khung tối thiểu (Mạnh) |

## Phân công

| Thành viên | Mảng việc | Mã task |
|---|---|---|
| Phạm Văn Minh (trưởng nhóm) | Điều phối, đặc tả mô hình, validator, duyệt code, ghép báo cáo | `MINH-n` |
| Tôn Thiện Khỏe | Sinh dữ liệu, solver, thực nghiệm | `KHOE-n` |
| Vũ Văn Mạnh | Phân tích dịch vụ, giao diện, slide | `MANH-n` |

Task cụ thể được giao và theo dõi trên CoReach.
