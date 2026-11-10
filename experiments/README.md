# Thực nghiệm hiệu năng xếp lịch thi và xếp lại khi có sự cố

## 1. Mục tiêu và phạm vi

Thực nghiệm đánh giá chất lượng nghiệm và thời gian xử lý của các phương pháp xếp lịch thi, đồng thời kiểm tra khả năng điều chỉnh lịch khi phát sinh sự cố. Kết quả dùng để lựa chọn chiến lược phù hợp cho các bộ dữ liệu `medium` và `large`.

Các bộ dữ liệu được lấy từ thư mục `data/`: `toy`, `toy_gen`, `medium` và `large`. Các phép đo được thực hiện tuần tự trên cùng một máy, hạn chế tác vụ nặng chạy đồng thời.

## 2. Phương pháp thực nghiệm

### 2.1. Hiệu năng giải lịch ban đầu

| Bộ dữ liệu        | Phương pháp                                   |       Số lần chạy |
| ----------------- | --------------------------------------------- | ----------------: |
| `toy`, `toy_gen`  | CP-SAT `single`, CP-SAT `two_phase`, PuLP/CBC | 3 lần/phương pháp |
| `medium`, `large` | CP-SAT `single`, CP-SAT `two_phase`           | 3 lần/phương pháp |

Tổng cộng **30 lần giải**: 24 lần CP-SAT và 6 lần PuLP/CBC.

Với CP-SAT, dùng `random_seed` lần lượt là `0`, `1`, `2`, `num_workers = 8` và `time_limit_sec = 300`. PuLP/CBC chạy một luồng và không sử dụng `random_seed`; ba lượt của mỗi bộ dữ liệu là các phép đo lặp, không phải ba cấu hình ngẫu nhiên khác nhau. CBC có cơ chế dừng cứng riêng nên thời gian thực tế có thể vượt 300 giây.

Các chỉ số đánh giá gồm trạng thái nghiệm, giá trị mục tiêu `Z`, thời gian giải, số vi phạm ràng buộc, số lượt thi và các KPI liên quan đến sinh viên, giám thị.

Khoảng cách tới cận dưới được tính theo:

`gap = (objective - best_bound) / objective`

Chỉ tính `gap` khi có đủ `objective`, `best_bound` và `objective` khác 0; trường hợp không có cận dưới thì để trống, không mặc định bằng 0. Với bài toán cực tiểu, **objective và gap càng thấp càng tốt**, với điều kiện lịch hợp lệ.

Một lượt được xem là có nghiệm hợp lệ khi trạng thái là `FEASIBLE` hoặc `OPTIMAL` và không có vi phạm ràng buộc cứng. Trường hợp `two_phase` chuyển sang `single` dự phòng được nhận diện bằng thông báo `S04` trong JSON; các lượt này cần được phân biệt khi phân tích hiệu quả riêng của hai pha.

### 2.2. Thời gian xếp lại khi có sự cố

Trên mỗi bộ `medium` và `large`, sử dụng lịch do CP-SAT `two_phase` với seed `0` tạo ra làm lịch ban đầu.

Ba kịch bản được kiểm tra:

1. Một phòng đang sử dụng bị hỏng trong một ca thi.
2. Một giám thị đang được phân công không thể coi thi trong cả ngày.
3. Hai phòng khác nhau bị hỏng tại hai ca, đồng thời một giám thị bận cả ngày.

Phòng, giám thị và thời điểm sự cố được chọn từ **lịch thực tế**, theo quy tắc xác định để có thể tái lập.

Mỗi kịch bản được đo một lần, tổng cộng **6 lần xếp lại**. Việc xếp lại sử dụng `src.reschedule.reschedule`, với chiến lược `single` và giới hạn solver theo `configs/default.json` (hiện là 45 giây).

`total_time_sec` đo từ ngay trước lúc gọi hàm `reschedule` đến khi hàm trả kết quả, bao gồm đọc dữ liệu, dựng mô hình, giải, hậu xử lý và ghi lịch ra JSON. Thời gian tạo lịch ban đầu không tính vào phép đo xếp lại.

Điều kiện đạt **KPI dưới 60 giây** là đồng thời thỏa mãn:

- Trạng thái `FEASIBLE` hoặc `OPTIMAL`.
- Không có vi phạm ràng buộc cứng (`violations = 0`).
- `total_time_sec < 60` giây.

## 3. Cách chạy thực nghiệm

Chạy các lệnh sau trong PowerShell tại thư mục gốc dự án:

```powershell
py -m pip install -r requirements.txt
py -m pytest -v

py experiments/perf.py
py experiments/reschedule_perf.py
py experiments/update_report.py
```

Script lưu kết quả sau mỗi lần chạy và bỏ qua các tổ hợp đã có trong CSV, nên có thể tiếp tục sau khi gián đoạn. Muốn chạy lại toàn bộ và thay thế kết quả cũ, dùng tùy chọn `--force` tương ứng.

Nên chạy `perf.py` trước để script xếp lại dùng cùng lịch nền seed `0`.

### Các tệp kết quả

| Đường dẫn                            | Nội dung                            |
| ------------------------------------ | ----------------------------------- |
| `experiments/results/perf.csv`       | Kết quả 30 lượt giải, 14 cột        |
| `experiments/results/reschedule.csv` | Kết quả 6 kịch bản xếp lại, 13 cột  |
| `experiments/README.md`              | Phương pháp, kết quả và đánh giá    |
| `docs/model_spec.md` (A.13)          | Bảng tóm tắt và kết luận            |
| `output/perf/`                       | Lịch giải chi tiết và thông tin máy |
| `output/reschedule_perf/`            | Lịch gốc và lịch sau sự cố          |

## 4. Môi trường thực nghiệm

Thông tin máy được ghi tại `output/perf/machine.json` và cập nhật tự động vào đây sau khi chạy `experiments/update_report.py`.

<!-- EXPERIMENT_MACHINE_BEGIN -->
- CPU: **11th Gen Intel(R) Core(TM) i5-11400H @ 2.70GHz** (12 luồng logic)
- RAM: **15.73 GB**
- Hệ điều hành: Windows-11-10.0.26300-SP0; Python: 3.13.7
- Giới hạn mỗi lượt: 300 giây; CP-SAT 8 workers; CBC một luồng.
<!-- EXPERIMENT_MACHINE_END -->

## 5. Kết quả thực nghiệm

Các bảng dưới đây được tổng hợp trực tiếp từ `perf.csv` và `reschedule.csv` bằng `experiments/update_report.py`. Chỉ đưa ra kết luận chính thức khi số liệu đã được thu thập đầy đủ.

<!-- EXPERIMENT_RESULTS_BEGIN -->
**Tiến độ:** 30/30 lượt giải; 6/6 kịch bản xếp lại.

| Bộ dữ liệu | Phương pháp | Nghiệm hợp lệ / lượt đo | OPTIMAL / lượt đo | Z TB (min–max) | Thời gian TB (s) | Gap TB |
|---|---|---:|---:|---:|---:|---:|
| toy | cp-sat / single | 3/3 | 3/3 | 2391.0 (2391–2391) | 12.0 | 0.000 |
| toy | cp-sat / two_phase | 3/3 | 3/3 | 2391.0 (2391–2391) | 4.3 | 0.000 |
| toy | pulp / single | 3/3 | 0/3 | 2391.0 (2391–2391) | 300.0 | — |
| toy_gen | cp-sat / single | 3/3 | 3/3 | 3650.0 (3650–3650) | 23.2 | 0.000 |
| toy_gen | cp-sat / two_phase | 3/3 | 0/3 | 3650.0 (3650–3650) | 8.4 | 0.005 |
| toy_gen | pulp / single | 3/3 | 0/3 | 3670.0 (3650–3710) | 300.2 | — |
| medium | cp-sat / single | 3/3 | 0/3 | 14994.7 (13609–16251) | 300.7 | 1.313 |
| medium | cp-sat / two_phase | 3/3 | 0/3 | 13050.3 (12268–14231) | 240.8 | 1.078 |
| large | cp-sat / single | 3/3 | 0/3 | 43494.0 (41950–46318) | 302.1 | 1.217 |
| large | cp-sat / two_phase | 3/3 | 0/3 | 38758.0 (37660–40018) | 242.6 | 1.238 |

Dấu «—» biểu thị thiếu giá trị để tính, không phải bằng 0. Thời gian trung bình tính trên các lượt đã ghi; Z/gap chỉ tính từ nghiệm hợp lệ.

### Fallback của `two_phase`

`S04` ghi nhận pha 2 không tìm được nghiệm và đã thử chuyển sang `single`; không đồng nghĩa fallback đã tìm được nghiệm. Khi đánh giá hai pha thuần túy, cần tách riêng các lượt này.

- `toy`: 0/3 lượt có thông báo `S04`.
- `toy_gen`: 0/3 lượt có thông báo `S04`.
- `medium`: 0/3 lượt có thông báo `S04`.
- `large`: 0/3 lượt có thông báo `S04`.

### Lựa chọn chiến lược

- **medium:** đề xuất `two_phase` (single 3/3 nghiệm hợp lệ, two_phase 3/3; Z TB 14994.7 / 13050.3; gap TB 1.313 / 1.078; thời gian TB 300.7s / 240.8s).
- **large:** đề xuất `two_phase` (single 3/3 nghiệm hợp lệ, two_phase 3/3; Z TB 43494.0 / 38758.0; gap TB 1.217 / 1.238; thời gian TB 302.1s / 242.6s).

### Xếp lại khi có sự cố

| Bộ dữ liệu | Kịch bản | Trạng thái | Tổng thời gian (s) | Vi phạm | KPI < 60s |
|---|---|---|---:|---:|---|
| medium | room_one_period | OPTIMAL | 23.534 | 0 | ĐẠT |
| medium | lecturer_whole_day | OPTIMAL | 24.778 | 0 | ĐẠT |
| medium | three_simultaneous | OPTIMAL | 25.105 | 0 | ĐẠT |
| large | room_one_period | FEASIBLE | 46.144 | 0 | ĐẠT |
| large | lecturer_whole_day | FEASIBLE | 46.080 | 0 | ĐẠT |
| large | three_simultaneous | FEASIBLE | 46.193 | 0 | ĐẠT |

**Kết luận xếp lại trên large:** đạt KPI dưới 60 giây trên cả ba kịch bản đã đo.

**Giới hạn:** Mỗi cấu hình solver được đo với ba seed; mỗi kịch bản xếp lại chỉ đo một lần. Kết quả phụ thuộc môi trường máy và dữ liệu thực nghiệm.
<!-- EXPERIMENT_RESULTS_END -->

## 6. Đánh giá và kết luận

Sau khi hoàn thành các phép đo, phân tích trên cơ sở bảng kết quả ở mục 5:

- **CP-SAT `two_phase` và `single`:** So sánh tỷ lệ tìm được nghiệm hợp lệ, objective, thời gian và gap trên `medium`, `large`; tách các lượt fallback trước khi đánh giá riêng `two_phase`.
- **CP-SAT và PuLP/CBC:** So sánh trên `toy`, `toy_gen` về khả năng tìm nghiệm, chứng minh tối ưu và thời gian; lưu ý ba lượt PuLP là phép đo lặp.
- **Chiến lược mặc định:** Ưu tiên khả năng tạo lịch hợp lệ, sau đó đối chiếu objective, gap và thời gian để đề xuất riêng cho `medium` và `large`.
- **Khả năng xếp lại:** Kiểm tra cả ba kịch bản trên `large` có đạt KPI dưới 60 giây hay không. Nếu không đạt, xem xét cố định phần lịch không bị ảnh hưởng, thu hẹp phạm vi tối ưu và tận dụng lịch cũ làm lời giải gợi ý rồi đo lại.

**Giới hạn đánh giá:** Các kết quả được đo trên một cấu hình máy; mỗi kịch bản xếp lại chỉ chạy một lần. Vì vậy, chúng phản ánh hiệu năng của các lần chạy đã đo, không phải bảo đảm cho mọi dữ liệu và môi trường triển khai. Kết luận lựa chọn chiến lược phải dựa trên số liệu thực nghiệm, không dựa vào kết quả tham khảo từ các lần đo trước.
