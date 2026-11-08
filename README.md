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

# Dùng solver đối chứng PuLP + CBC thay cho CP-SAT
python -m src.run --data data/toy --solver pulp

# Mở giao diện xem lịch
streamlit run app/app.py

# Xếp lại khi có sự cố: phòng G2-LAB1 hỏng ca 3 ngày 15/12 (kết quả ghi vào output/toy/reschedule.json)
python -m src.reschedule --data data/toy --base tests/reference/toy_schedule.json --incident room,G2-LAB1,2026-12-15,3

# Chạy kiểm thử
pytest
```

### Giao diện

Giao diện có bốn tab:

- Xem kết quả: mặc định mở kết quả tham chiếu `tests/reference/toy_schedule.json`. Có thể tải lên file JSON khác
  hoặc nhập đường dẫn file kết quả; file tải lên được ưu tiên. Sau khi chạy ở tab thứ hai, tab này hiện ngay kết quả vừa chạy.
- Nhập dữ liệu và xếp lịch: chọn bộ dữ liệu có sẵn hoặc tải CSV lên, xem thông báo kiểm tra dữ liệu, chỉnh cấu hình,
  chọn solver CP-SAT hoặc PuLP rồi chạy.
- So sánh hai lịch: bảng KPI và điểm phạt cạnh nhau, các lượt bị đổi (dời ca, đổi phòng, đổi giám thị), số sinh viên và
  giám thị bị ảnh hưởng. Dùng `diff_schedules` trong `src/reschedule.py` (data_schema mục 7.6).
- Sự cố và xếp lại: chọn lịch gốc, khai báo một hoặc nhiều sự cố (phòng hoặc giảng viên, ngày, ca hoặc cả ngày), bấm
  "Xếp lại" để gọi `reschedule`; kết quả ghi vào `output/<tên bộ dữ liệu>/reschedule.json` và được so sánh với lịch gốc.
  Nếu không xếp lại được, giao diện hiện nguyên nhân và kết quả chẩn đoán.

Phần xem kết quả:

- Tổng quan có trạng thái, mục tiêu, cận dưới, thời gian giải, điểm phạt A-S1 đến A-S6
  chưa nhân trọng số và toàn bộ KPI (kèm giải thích tiếng Việt). Giá trị `null` không được coi là 0.
- Thông báo chia theo lỗi/cảnh báo/thông tin; vi phạm ràng buộc cứng được tô nổi bật.
- Lịch ngày × 4 ca hiển thị môn và phòng; lượt thi hai ca xuất hiện ở cả hai ô.
- Các tab cho phép chọn phòng, nhập mã sinh viên hoặc chọn mã giảng viên để tra cứu.
  Giờ là khung giữ phòng; file kết quả không chứa tên giảng viên.
- Nút **Xuất Excel** tạo hai sheet: **Lịch tổng** (mỗi phòng/lượt một dòng) và
  **Sinh viên theo phòng** (mỗi sinh viên/phòng/lượt một dòng).
- `INPUT_ERROR`, `INFEASIBLE`, `UNKNOWN` chỉ hiển thị tổng quan và thông báo,
  không vẽ lịch hoặc cho xuất lịch.

Kiểm thử giao diện: `pytest tests/test_app.py`. Test chạy bằng AppTest trên bản sao dữ liệu toy trong
thư mục tạm (biến môi trường `EXAM_APP_DATA_DIR`, `EXAM_APP_OUTPUT_DIR`), không ghi vào `data/` và `output/` của repo.

## Cấu trúc thư mục

```
├── docs/                  Tài liệu: phạm vi, mô hình, định dạng dữ liệu
├── configs/default.json   Cấu hình mặc định (data_schema mục 6)
├── data/toy/              Bộ dữ liệu nhỏ dùng để kiểm thử (xem data/toy/README.md)
├── output/               Kết quả các lần chạy (không commit)
├── src/
│   ├── instance.py        Cấu trúc dữ liệu dùng chung, giao diện SolveResult của solver
│   ├── config.py          Đọc cấu hình
│   ├── data_loader.py     Đọc và kiểm tra dữ liệu (mã D, P)
│   ├── exam_solver.py     Solver bài toán A (CP-SAT)
│   ├── exam_solver_pulp.py  Solver đối chứng bài toán A (PuLP + CBC)
│   ├── room_solver.py     Solver bài toán B
│   ├── schedule.py        Hậu xử lý, dựng schedule.json
│   ├── validator.py       Kiểm tra lời giải độc lập với solver
│   ├── kpi.py             Tính KPI và tính lại điểm phạt
│   ├── generator.py       Sinh dữ liệu giả lập
│   ├── run.py             Chạy toàn bộ quy trình
│   ├── reschedule.py      Xếp lại khi có sự cố, so sánh hai lịch
│   └── diagnose.py        Chẩn đoán nguyên nhân khi vô nghiệm
├── app/app.py             Giao diện Streamlit
├── tests/                 Kiểm thử (pytest); tests/reference/toy_schedule.json là kết quả tham chiếu của bộ toy
├── experiments/           Script và kết quả thực nghiệm
└── report/                Báo cáo
```

## Trạng thái các thành phần

| Thành phần | Trạng thái |
|---|---|
| `data_loader.py`, `config.py`, `instance.py` | Hoàn chỉnh, có kiểm thử |
| `validator.py`, `kpi.py`, `schedule.py`, `run.py` | Hoàn chỉnh, có kiểm thử. Khi vô nghiệm, `run.py` tự chẩn đoán nguyên nhân (tắt bằng `--no-diagnose`) |
| `reschedule.py`, `diagnose.py` | Hoàn chỉnh, có kiểm thử: xếp lại khi có sự cố sao cho ít thay đổi nhất (model_spec A.14), chẩn đoán khi vô nghiệm (A.8) |
| `generator.py` | Hoàn chỉnh, có kiểm thử; dữ liệu sinh sẵn (seed 1) trong `data/toy_gen`, `data/medium`, `data/large` |
| `exam_solver.py` | Chiến lược `single` hoàn chỉnh, có kiểm thử: trên `toy` đạt `OPTIMAL` 2391 trong khoảng 20 giây. Chiến lược `two_phase` hoàn chỉnh (KHOE-3), trên `toy` đạt 2391 trong khoảng 7 giây |
| `exam_solver_pulp.py` | Hoàn chỉnh, có kiểm thử. Trên `toy` tìm được lời giải tối ưu 2391 nhưng không chứng minh được tối ưu trong vài phút (model_spec A.13) |
| `room_solver.py` | Chờ spec bài toán B (Minh viết spec, Khỏe cài đặt) |
| `app/app.py` | Xem và so sánh lịch, kiểm tra dữ liệu, chạy solver (CP-SAT/PuLP), khai báo sự cố và xếp lại; có AppTest |

## Phân công

| Thành viên | Mảng việc | Mã task |
|---|---|---|
| Phạm Văn Minh | Điều phối, đặc tả mô hình, validator, duyệt code, ghép báo cáo | `MINH-n` |
| Tôn Thiện Khỏe | Sinh dữ liệu, solver, thực nghiệm | `KHOE-n` |
| Vũ Văn Mạnh | Phân tích dịch vụ, giao diện, slide | `MANH-n` |

Task cụ thể được giao và theo dõi trên CoReach.
