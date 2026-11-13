# BTL-KHDV — Hệ thống xếp lịch phòng thi và phòng máy học phần

Bài tập lớn môn Khoa học Dịch vụ. Hệ thống dùng mô hình quy hoạch nguyên tuyến tính (ILP), giải bằng Google OR-Tools CP-SAT, để tự động xếp:

- Lịch thi cuối kỳ: môn nào thi ca nào, ở phòng nào, giám thị nào coi (bài toán A);
- Lịch phòng học / phòng máy thực hành theo tuần: lớp nào học ca nào, ở phòng nào (bài toán B).

## Tài liệu

Đọc theo thứ tự trước khi viết code:

| Tài liệu                                   | Nội dung                                            |
| ------------------------------------------ | --------------------------------------------------- |
| [docs/scope.md](docs/scope.md)             | Phạm vi đề tài, giả định, ràng buộc, KPI            |
| [docs/model_spec.md](docs/model_spec.md)   | Đặc tả mô hình toán (bài toán A và B)               |
| [docs/data_schema.md](docs/data_schema.md) | Định dạng dữ liệu đầu vào, cấu hình và file kết quả |
| [CONTRIBUTING.md](CONTRIBUTING.md)         | Quy ước làm việc nhóm: nhánh, commit, Pull Request  |

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

Cài đặt thành công khi `pytest` báo toàn bộ passed (mất khoảng 5 phút vì có các ca giải bằng CP-SAT và PuLP).

Các lệnh bên dưới đều chạy trong môi trường `.venv` đã kích hoạt, từ thư mục gốc của repo.

## Chạy

```powershell
# Xếp lịch thi cho một bộ dữ liệu, ghi kết quả vào output/<tên bộ dữ liệu>/schedule.json
python -m src.run --data data/toy

# Dùng solver đối chứng PuLP + CBC thay cho CP-SAT
python -m src.run --data data/toy --solver pulp

# Xếp lịch phòng học/phòng máy theo tuần (bài toán B), ghi kết quả vào output/<tên bộ dữ liệu>/timetable.json
python -m src.run --problem B --data data/toy_b --config configs/problem_b.json

# Sinh dữ liệu và chạy thực nghiệm bài B
python -m src.generator --size medium_b --seed 1 --out data/medium_b
python -m src.generator --size large_b --seed 1 --out data/large_b
python -m experiments.perf_b --seeds 0 1 2 --time-limit 300 --workers 8

# Mở giao diện (cả bài A và bài B)
streamlit run app/app.py

# Xếp lại khi có sự cố: phòng G2-LAB1 hỏng ca 3 ngày 15/12 (kết quả ghi vào output/toy/reschedule.json)
python -m src.reschedule --data data/toy --base tests/reference/toy_schedule.json --incident room,G2-LAB1,2026-12-15,3

# Chạy kiểm thử
pytest
```

### Giao diện

Giao diện có tám tab: năm tab của bài A (dưới đây) và ba tab của bài B (mục "Giao diện bài toán B").

Năm tab của bài A:

- Xem kết quả: mặc định mở kết quả tham chiếu `tests/reference/toy_schedule.json`. Có thể tải lên file JSON khác
  hoặc nhập đường dẫn file kết quả; file tải lên được ưu tiên. Sau khi chạy ở tab thứ hai, tab này hiện ngay kết quả vừa chạy.
- Nhập dữ liệu và xếp lịch: chọn bộ dữ liệu có sẵn hoặc tải CSV lên, xem thông báo kiểm tra dữ liệu, chỉnh cấu hình,
  chọn solver CP-SAT hoặc PuLP rồi chạy.
- So sánh hai lịch: bảng KPI và điểm phạt cạnh nhau, các lượt bị đổi (dời ca, đổi phòng, đổi giám thị), số sinh viên và
  giám thị bị ảnh hưởng. Dùng `diff_schedules` trong `src/reschedule.py` (data_schema mục 7.6).
- Sự cố và xếp lại: chọn lịch gốc, khai báo một hoặc nhiều sự cố (phòng hoặc giảng viên, ngày, ca hoặc cả ngày), bấm
  "Xếp lại" để gọi `reschedule`; kết quả ghi vào `output/<tên bộ dữ liệu>/reschedule.json` và được so sánh với lịch gốc.
  Nếu không xếp lại được, giao diện hiện nguyên nhân và kết quả chẩn đoán.
- Kết quả thực nghiệm: đọc `perf.csv`, `reschedule.csv`, `sensitivity.csv` trong `experiments/results/`
  (có thể đổi qua `EXAM_APP_RESULTS_DIR`). Biểu đồ thời gian giải trung bình theo seed và bảng mục tiêu/cận dưới/gap
  lọc theo bộ dữ liệu; thời gian xếp lại theo kịch bản với ngưỡng 60 giây, kèm mức tăng Z và đánh giá đạt thời gian,
  đạt chất lượng (Z không tăng quá 10%) theo cùng tiêu chí với `experiments/update_report.py`; đường đánh đổi P1/P6,
  mỗi seed một đường; độ nhạy điểm phạt, KPI theo hệ số nhân của trọng số đã chọn (hệ số 1 lấy từ thí nghiệm noise
  seed 0); bảng cho các thí nghiệm noise, param, time_limit, reschedule_weight. Mỗi bảng đang xem có nút tải CSV;
  file thiếu hoặc sai cột chỉ báo lỗi trong phần tương ứng.

Phần xem kết quả:

- Tổng quan có trạng thái, mục tiêu, cận dưới, thời gian giải, điểm phạt A-S1 đến A-S6
  chưa nhân trọng số và toàn bộ KPI (kèm giải thích tiếng Việt). Giá trị `null` không được coi là 0.
- Thông báo chia theo lỗi/cảnh báo/thông tin; vi phạm ràng buộc cứng được tô nổi bật.
- Lịch ngày × 4 ca hiển thị môn và phòng; lượt thi hai ca xuất hiện ở cả hai ô.
- Các tab cho phép chọn phòng, nhập mã sinh viên hoặc chọn mã giảng viên để tra cứu.
  Giờ là khung giữ phòng; file kết quả không chứa tên giảng viên.
- Nút "Xuất Excel" tạo hai sheet: "Lịch tổng" (mỗi phòng/lượt một dòng) và
  "Sinh viên theo phòng" (mỗi sinh viên/phòng/lượt một dòng).
- `INPUT_ERROR`, `INFEASIBLE`, `UNKNOWN` chỉ hiển thị tổng quan và thông báo,
  không vẽ lịch hoặc cho xuất lịch.

Kiểm thử giao diện: `pytest tests/test_app.py`. Test chạy bằng AppTest trên bản sao dữ liệu toy trong
thư mục tạm (biến môi trường `EXAM_APP_DATA_DIR`, `EXAM_APP_OUTPUT_DIR`), không ghi vào `data/` và `output/` của repo.

## Giao diện bài toán B

- Lịch học tuần B: chọn bộ dữ liệu B (bộ có `week_slots.csv` và `classes.csv`, mặc định `toy_b`; danh sách của bài A không chứa các bộ này). Nguồn "Kết quả đã lưu" đọc `output/<tên bộ dữ liệu>/timetable.json`; nút "Chạy xếp lịch B" giải bằng CP-SAT với `configs/problem_b.json`, ghi file đó rồi hiển thị ngay. Nguồn "Mẫu toy_b tham chiếu" mở lịch tối ưu cố định `tests/reference/toy_timetable.json` (Z = 355), chỉ dùng cho `toy_b`.
- Lưới Thứ × ca và danh sách buổi lọc đồng thời theo phòng, giảng viên, nhóm bắt buộc (nhóm không chứa lớp tự chọn). Bảng KPI tính trên toàn lịch, tính lại từ dữ liệu đầu vào chứ không đọc số trong JSON. Excel xuất các buổi đang lọc và KPI toàn lịch. Lịch có vi phạm ràng buộc cứng thì chỉ hiện danh sách vi phạm, không hiện lịch và không cho xuất.
- Sự cố B: khai báo một phòng hoặc giảng viên bận ở một ca, hoặc thêm lớp; xem các buổi bị ảnh hưởng trực tiếp và xuất `incidents_b.json` (dạng nháp `B-incident-draft-v1`). Nút xếp lại đang khóa cho đến khi có bộ xếp lại B (model_spec B.9, task MINH-6). Có thể nhập đường dẫn một `retimetable.json` để so sánh với lịch đang mở.
- Thực nghiệm B: đọc `perf_b.csv` và `lab_reserve_b.csv` do `experiments/perf_b.py` ghi trong `experiments/results/` (đổi được qua `EXAM_APP_RESULTS_DIR`). Biểu đồ thời gian giải theo bộ dữ liệu và seed, kèm mốc 5 phút; bảng so sánh tắt/bật B-S4 theo số buổi máy phải dời ca, số buổi chỉ cần đổi phòng và số ca vượt ngưỡng dự phòng khi một phòng máy hỏng. Ô "Dùng dữ liệu mẫu tổng hợp" đọc `experiments/samples/`, chỉ để xem giao diện.
- Kiểm thử: `pytest tests/test_kpi_b.py tests/test_app_b.py tests/test_app_experiments_b.py`.

## Cấu trúc thư mục

```
├── docs/                  Tài liệu: phạm vi, mô hình, định dạng dữ liệu
├── configs/default.json   Cấu hình mặc định (data_schema mục 6)
├── configs/problem_b.json Cấu hình bài toán B (data_schema mục 9.8)
├── data/toy/              Bộ dữ liệu nhỏ dùng để kiểm thử (xem data/toy/README.md)
├── data/toy_b/            Bộ dữ liệu nhỏ của bài toán B, viết tay, đáp án 355 (xem data/toy_b/README.md)
├── data/medium_b, large_b Bộ dữ liệu B sinh tự động (seed 1)
├── output/               Kết quả các lần chạy (không commit)
├── src/
│   ├── instance.py        Cấu trúc dữ liệu dùng chung, giao diện SolveResult của solver
│   ├── config.py          Đọc cấu hình
│   ├── data_loader.py     Đọc và kiểm tra dữ liệu (mã D, P)
│   ├── instance_b.py      Cấu trúc dữ liệu bài toán B, giao ước đầu vào/đầu ra của room_solver
│   ├── data_loader_b.py   Đọc và kiểm tra dữ liệu bài toán B (mã D, PB)
│   ├── validator_b.py     Kiểm tra lịch học bài toán B độc lập với solver, tính lại điểm phạt
│   ├── exam_solver.py     Solver bài toán A (CP-SAT)
│   ├── exam_solver_pulp.py  Solver đối chứng bài toán A (PuLP + CBC)
│   ├── room_solver.py     Solver bài toán B
│   ├── generator_b.py     Sinh medium_b/large_b
│   ├── timetable.py       Hậu xử lý bài B, dựng timetable.json
│   ├── kpi_b.py           Tính KPI bài B
│   ├── schedule.py        Hậu xử lý, dựng schedule.json
│   ├── validator.py       Kiểm tra lời giải độc lập với solver
│   ├── kpi.py             Tính KPI và tính lại điểm phạt
│   ├── generator.py       Sinh dữ liệu giả lập
│   ├── run.py             Chạy toàn bộ quy trình
│   ├── reschedule.py      Xếp lại khi có sự cố, so sánh hai lịch
│   └── diagnose.py        Chẩn đoán nguyên nhân khi vô nghiệm
├── app/app.py             Giao diện Streamlit; tab bài B nằm ở app/timetable_b.py, app/experiments_b.py
├── tests/                 Kiểm thử (pytest); tests/reference/ chứa kết quả tham chiếu của toy và toy_b
├── experiments/           Script và kết quả thực nghiệm
└── report/                Báo cáo
```

## Trạng thái các thành phần

| Thành phần                                        | Trạng thái                                                                                                                                                                                 |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `data_loader.py`, `config.py`, `instance.py`      | Hoàn chỉnh, có kiểm thử                                                                                                                                                                    |
| `validator.py`, `kpi.py`, `schedule.py`, `run.py` | Có kiểm thử. `run.py` định tuyến A/B theo cấu hình hoặc `--problem B`; tự chẩn đoán khi vô nghiệm hiện chỉ áp dụng A                                                                       |
| `reschedule.py`, `diagnose.py`                    | Hoàn chỉnh, có kiểm thử: xếp lại khi có sự cố sao cho ít thay đổi nhất (model_spec A.14), chẩn đoán khi vô nghiệm (A.8)                                                                    |
| `generator.py`, `generator_b.py`                  | Có kiểm thử; sinh dữ liệu A và medium_b/large_b. Các bộ sinh sẵn dùng seed 1; B dùng nguyên file phòng và giảng viên của A                                                                 |
| `exam_solver.py`                                  | Chiến lược `single` hoàn chỉnh, có kiểm thử: trên `toy` đạt `OPTIMAL` 2391 trong khoảng 20 giây. Chiến lược `two_phase` hoàn chỉnh (KHOE-3), trên `toy` đạt 2391 trong khoảng 7 giây       |
| `exam_solver_pulp.py`                             | Hoàn chỉnh, có kiểm thử. Trên `toy` tìm được lời giải tối ưu 2391 nhưng không chứng minh được tối ưu trong vài phút (model_spec A.13)                                                      |
| `instance_b.py`, `data_loader_b.py`               | Hoàn chỉnh, có kiểm thử: đọc dữ liệu bài toán B, kiểm tra PB1–PB7 (model_spec B.7). `data_loader.load_instance` tự chuyển sang bộ đọc B khi cấu hình có `"problem": "B"`                   |
| `validator_b.py`                                  | Hoàn chỉnh, có kiểm thử: soát B-H1 đến B-H7 trên mảng `sessions` của `timetable.json`, tính lại B-S1 đến B-S4. Lịch tối ưu mẫu của `toy_b` (Z = 355) nằm trong `tests/test_validator_b.py` |
| `room_solver.py`, `timetable.py`, `kpi_b.py`      | Hoàn chỉnh, có kiểm thử: toy_b đạt OPTIMAL 355 dưới 1 giây, medium_b và large_b đạt OPTIMAL (large_b khoảng 9 giây). Solver hỗ trợ bỏ nhóm B-H5/B-H7/B-H6 để chẩn đoán. Xem experiments/README.md mục bài toán B |
| `app/app.py`                                      | Bài A: xem/so sánh lịch, chạy solver, sự cố/xếp lại, thực nghiệm. Bài B: chạy solver và xem lịch tuần, KPI, xuất Excel, khai báo sự cố, thực nghiệm. Có AppTest                                       |

## Việc còn lại của bài toán B

- Chẩn đoán tự động khi bài B vô nghiệm: `run.py --problem B` hiện báo `INFEASIBLE` nhưng chưa gọi chẩn đoán (model_spec B.7, task MINH-6).
- Xếp lại khi có sự cố (model_spec B.9, task MINH-6): cần thêm vào `room_solver.solve` tùy chọn giữ cố định một phần lịch cũ, gợi ý lời giải và phạt thay đổi B-R1, B-R2; sau đó mở khóa nút "Xếp lại B" ở tab Sự cố B.

## Phân công

| Thành viên     | Mảng việc                                                      | Mã task  |
| -------------- | -------------------------------------------------------------- | -------- |
| Phạm Văn Minh  | Điều phối, đặc tả mô hình, validator, duyệt code, ghép báo cáo | `MINH-n` |
| Tôn Thiện Khỏe | Sinh dữ liệu, solver, thực nghiệm                              | `KHOE-n` |
| Vũ Văn Mạnh    | Phân tích dịch vụ, giao diện, slide                            | `MANH-n` |

Task cụ thể được giao và theo dõi trên CoReach.
