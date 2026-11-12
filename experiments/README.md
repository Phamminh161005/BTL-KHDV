# Thực nghiệm

## Hợp đồng CSV tạm thời cho giao diện bài toán B

`app.experiments_b.page_experiments_b(results_dir: Path)` là trang độc lập để ứng dụng chính gọi khi tích hợp. Theo mặc định chỉ đọc `perf_b.csv` và `lab_reserve_b.csv` trong đúng `results_dir` được truyền vào; không chạy solver, không ghi kết quả và không tự chuyển sang dữ liệu mẫu. Ô chọn **Dùng dữ liệu mẫu tổng hợp** mới đọc `experiments/samples/` và luôn gắn nhãn synthetic. Hai file mẫu chỉ minh họa giao diện, **không phải phép đo hoặc kết quả solver B**. Chưa có solver B hay header KHOE-5 chính thức; hợp đồng dưới đây là quy ước tạm thời được chấp thuận, cần đối chiếu trước khi nối pipeline xuất CSV thật.

Mỗi file dùng UTF-8 (có thể có BOM), hàng đầu là tên cột phân biệt chữ thường/chữ hoa, các hàng sau là một lần chạy/seed. Cột bổ sung được giữ nếu có, nhưng dashboard chỉ dùng các cột được liệt kê. Lỗi header khiến cả file bị bỏ qua; lỗi giá trị chỉ bỏ qua dòng đó, cảnh báo kèm tên file và số dòng. File còn lại vẫn được hiển thị độc lập.

| File | Cột bắt buộc | Cột tùy chọn |
|---|---|---|
| `perf_b.csv` | `dataset,seed,status,solve_time_sec,time_limit_sec` | `objective,best_bound,solver,strategy` |
| `lab_reserve_b.csv` | `dataset,seed,reserve_enabled,lab_reserve_ratio,status,solve_time_sec,room_utilization_lab,lab_peak_utilization,slots_without_lab_reserve` | `solver,strategy` và các cột metadata khác |

`dataset` là tên không rỗng; `seed` là số nguyên không âm. `status` nhận `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `UNKNOWN`, `INPUT_ERROR` (không phân biệt hoa/thường); `FEASIBLE` là có lịch hợp lệ nhưng chưa chứng minh tối ưu. Thời gian đo bằng giây hữu hạn không âm; `time_limit_sec` phải dương. `objective` là số không âm hữu hạn bắt buộc khi có nghiệm, để trống khi không có nghiệm; `best_bound` là số không âm hữu hạn hoặc trống nếu chưa có cận. Không tổng hợp objective qua seed hay so giữa các chế độ dự trữ vì cấu hình/hàm mục tiêu có thể khác nhau.

`reserve_enabled` nhận `true`/`false`; `lab_reserve_ratio`, `room_utilization_lab`, `lab_peak_utilization` là tỷ lệ trong `[0,1]`; `slots_without_lab_reserve` là số ca nguyên không âm. Các KPI lab có thể để trống nếu trạng thái không có nghiệm; với `OPTIMAL`/`FEASIBLE` phải có đủ KPI. Mỗi file không được lặp cùng `(dataset, seed, solver, strategy)` (lab thêm `lab_reserve_ratio, reserve_enabled`). So sánh bật/tắt chỉ ghép những cặp cùng dataset, seed, tỷ lệ dự trữ, solver, strategy và cả hai có nghiệm; KPI và thời gian tổng hợp là trung bình trên các cặp đó. Biểu đồ hiệu năng dùng đường tham chiếu **300 giây = 5 phút**, không khẳng định mọi lượt có cùng time limit.

Tài liệu gồm hai phần: mục 1–6 là thực nghiệm hiệu năng các cách giải và thời gian xếp lại khi có sự cố (KHOE-4); mục 7 là độ nhạy trọng số và đường cong đánh đổi (MINH-4).

## 1. Mục tiêu và phạm vi

Thực nghiệm đánh giá chất lượng nghiệm và thời gian xử lý của các phương pháp xếp lịch thi, đồng thời kiểm tra khả năng điều chỉnh lịch khi phát sinh sự cố. Kết quả dùng để lựa chọn chiến lược phù hợp cho các bộ dữ liệu `medium` và `large`.

Các bộ dữ liệu được lấy từ thư mục `data/`: `toy`, `toy_gen`, `medium` và `large`. Các phép đo được thực hiện tuần tự trên cùng một máy, hạn chế tác vụ nặng chạy đồng thời.

## 2. Phương pháp thực nghiệm

### 2.1. Hiệu năng giải lịch ban đầu

| Bộ dữ liệu        | Phương pháp                                   |       Số lần chạy |
| ----------------- | --------------------------------------------- | ----------------: |
| `toy`, `toy_gen`  | CP-SAT `single`, CP-SAT `two_phase`, PuLP/CBC | 3 lần/phương pháp |
| `medium`, `large` | CP-SAT `single`, CP-SAT `two_phase`           | 3 lần/phương pháp |

Tổng cộng 30 lần giải: 24 lần CP-SAT và 6 lần PuLP/CBC.

Với CP-SAT, dùng `random_seed` lần lượt là `0`, `1`, `2`, `num_workers = 8` và `time_limit_sec = 300`. PuLP/CBC chạy một luồng và không sử dụng `random_seed`; ba lượt của mỗi bộ dữ liệu là các phép đo lặp, không phải ba cấu hình ngẫu nhiên khác nhau. CBC có cơ chế dừng cứng riêng nên thời gian thực tế có thể vượt 300 giây.

Các chỉ số đánh giá gồm trạng thái nghiệm, giá trị mục tiêu `Z`, thời gian giải, số vi phạm ràng buộc, số lượt thi và các KPI liên quan đến sinh viên, giám thị.

Khoảng cách tới cận dưới được tính theo:

`gap = (objective - max(best_bound, 0)) / objective`

Chỉ tính `gap` khi có đủ `objective`, `best_bound` và `objective` khác 0; trường hợp không có cận dưới thì để trống, không mặc định bằng 0. Vì Z là tổng các điểm phạt không âm nên Z luôn lớn hơn hoặc bằng 0; cận dưới âm (CP-SAT báo như vậy trên `medium` và `large`) không cho thông tin gì hơn cận 0 nên được thay bằng 0. Do đó gap nằm trong khoảng 0 đến 1: gap bằng 0 là đã chứng minh tối ưu, gap bằng 1 là chưa chứng minh được gì. Cột `best_bound` trong CSV vẫn giữ giá trị gốc solver báo. Với bài toán cực tiểu, objective và gap càng thấp càng tốt, với điều kiện lịch hợp lệ.

Một lượt được xem là có nghiệm hợp lệ khi trạng thái là `FEASIBLE` hoặc `OPTIMAL` và không có vi phạm ràng buộc cứng. Trường hợp `two_phase` chuyển sang `single` dự phòng được nhận diện bằng thông báo `S04` trong JSON; các lượt này cần được phân biệt khi phân tích hiệu quả riêng của hai pha.

### 2.2. Thời gian xếp lại khi có sự cố

Trên mỗi bộ `medium` và `large`, sử dụng lịch do CP-SAT `two_phase` với seed `0` tạo ra làm lịch ban đầu.

Ba kịch bản được kiểm tra:

1. Một phòng đang sử dụng bị hỏng trong một ca thi.
2. Một giám thị đang được phân công không thể coi thi trong cả ngày.
3. Hai phòng khác nhau bị hỏng tại hai ca, đồng thời một giám thị bận cả ngày.

Phòng, giám thị và thời điểm sự cố được chọn từ lịch thực tế, theo quy tắc xác định để có thể tái lập.

Mỗi kịch bản được đo một lần, tổng cộng 6 lần xếp lại. Việc xếp lại sử dụng `src.reschedule.reschedule`, với chiến lược `single` và giới hạn solver theo `configs/default.json` (hiện là 45 giây), giải hai bước: xếp lại cục bộ rồi giải trên toàn lịch (mục 6.4, model_spec A.14).

`total_time_sec` đo từ ngay trước lúc gọi hàm `reschedule` đến khi hàm trả kết quả, bao gồm đọc dữ liệu, dựng mô hình, giải, hậu xử lý và ghi lịch ra JSON. Thời gian tạo lịch ban đầu không tính vào phép đo xếp lại.

Mỗi kịch bản được đánh giá theo hai tiêu chí riêng.

Thời gian (KPI dưới 60 giây trong scope) đạt khi đồng thời thỏa mãn:

- Trạng thái `FEASIBLE` hoặc `OPTIMAL`.
- Không có vi phạm ràng buộc cứng (`violations = 0`).
- `total_time_sec < 60` giây.

Chất lượng đạt khi thời gian đạt và Z của lịch mới không tăng quá 10% so với lịch cũ (`objective_after <= 1,1 × objective_before`). Tiêu chí này được thêm vì chỉ đo thời gian thì một lần xếp lại xáo trộn gần hết lịch vẫn được tính là đạt. Ngưỡng 10% do nhóm tự chọn: một sự cố nhỏ (một phòng, một giảng viên) chỉ nên ảnh hưởng một phần nhỏ của lịch. Bảng kết quả ghi kèm số lượt thay đổi và số sinh viên bị ảnh hưởng để người đọc tự đánh giá mức xáo trộn.

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

Thông tin máy được ghi tại `output/perf/machine.json` và cập nhật tự động vào đây sau khi chạy `experiments/update_report.py`. Đây là máy đo `perf.csv`; `reschedule.csv` được đo lại trên một máy khác (mục 6.4).

<!-- EXPERIMENT_MACHINE_BEGIN -->
- CPU: 11th Gen Intel(R) Core(TM) i5-11400H @ 2.70GHz (12 luồng logic)
- RAM: 15.73 GB
- Hệ điều hành: Windows-11-10.0.26300-SP0; Python: 3.13.7
- Giới hạn mỗi lượt: 300 giây; CP-SAT 8 workers; CBC một luồng.
<!-- EXPERIMENT_MACHINE_END -->

## 5. Kết quả thực nghiệm

Các bảng dưới đây được tổng hợp trực tiếp từ `perf.csv` và `reschedule.csv` bằng `experiments/update_report.py`. Chỉ đưa ra kết luận chính thức khi số liệu đã được thu thập đầy đủ.

<!-- EXPERIMENT_RESULTS_BEGIN -->
Tiến độ: 30/30 lượt giải; 6/6 kịch bản xếp lại.

| Bộ dữ liệu | Phương pháp | Nghiệm hợp lệ / lượt đo | OPTIMAL / lượt đo | Z TB (min–max) | Thời gian TB (s) | Gap TB |
|---|---|---:|---:|---:|---:|---:|
| toy | cp-sat / single | 3/3 | 3/3 | 2391.0 (2391–2391) | 12.0 | 0.000 |
| toy | cp-sat / two_phase | 3/3 | 3/3 | 2391.0 (2391–2391) | 4.3 | 0.000 |
| toy | pulp / single | 3/3 | 0/3 | 2391.0 (2391–2391) | 300.0 | — |
| toy_gen | cp-sat / single | 3/3 | 3/3 | 3650.0 (3650–3650) | 23.2 | 0.000 |
| toy_gen | cp-sat / two_phase | 3/3 | 0/3 | 3650.0 (3650–3650) | 8.4 | 0.005 |
| toy_gen | pulp / single | 3/3 | 0/3 | 3670.0 (3650–3710) | 300.2 | — |
| medium | cp-sat / single | 3/3 | 0/3 | 14994.7 (13609–16251) | 300.7 | 1.000 |
| medium | cp-sat / two_phase | 3/3 | 0/3 | 13050.3 (12268–14231) | 240.8 | 1.000 |
| large | cp-sat / single | 3/3 | 0/3 | 43494.0 (41950–46318) | 302.1 | 1.000 |
| large | cp-sat / two_phase | 3/3 | 0/3 | 38758.0 (37660–40018) | 242.6 | 1.000 |

Dấu «—» biểu thị thiếu giá trị để tính, không phải bằng 0. Thời gian trung bình tính trên các lượt đã ghi; Z/gap chỉ tính từ nghiệm hợp lệ. Cận dưới âm được kẹp về 0 vì Z không âm, nên gap = 1 nghĩa là chưa chứng minh được gì.

### Fallback của `two_phase`

`S04` ghi nhận pha 2 không tìm được nghiệm và đã thử chuyển sang `single`; không đồng nghĩa fallback đã tìm được nghiệm. Khi đánh giá hai pha thuần túy, cần tách riêng các lượt này.

- `toy`: 0/3 lượt có thông báo `S04`.
- `toy_gen`: 0/3 lượt có thông báo `S04`.
- `medium`: 0/3 lượt có thông báo `S04`.
- `large`: 0/3 lượt có thông báo `S04`.

### Lựa chọn chiến lược

- medium: đề xuất `two_phase` (single 3/3 nghiệm hợp lệ, two_phase 3/3; Z TB 14994.7 / 13050.3; gap TB 1.000 / 1.000; thời gian TB 300.7s / 240.8s).
- large: đề xuất `two_phase` (single 3/3 nghiệm hợp lệ, two_phase 3/3; Z TB 43494.0 / 38758.0; gap TB 1.000 / 1.000; thời gian TB 302.1s / 242.6s).

### Xếp lại khi có sự cố

Hai tiêu chí được đánh giá riêng. Thời gian: có lịch hợp lệ và tổng thời gian dưới 60 giây (KPI trong scope). Chất lượng: Z của lịch mới không tăng quá 10% so với lịch cũ.

| Bộ dữ liệu | Kịch bản | Trạng thái | Tổng thời gian (s) | Z trước → sau | Lượt thay đổi / dời ca | SV bị ảnh hưởng | Thời gian | Chất lượng |
|---|---|---|---:|---:|---:|---:|---|---|
| medium | room_one_period | FEASIBLE | 42.551 | 12507 → 12507 (+0.0%) | 1 / 0 | 27 | ĐẠT | ĐẠT |
| medium | lecturer_whole_day | FEASIBLE | 44.064 | 12507 → 12507 (+0.0%) | 1 / 0 | 0 | ĐẠT | ĐẠT |
| medium | three_simultaneous | FEASIBLE | 45.744 | 12507 → 12527 (+0.2%) | 3 / 0 | 56 | ĐẠT | ĐẠT |
| large | room_one_period | FEASIBLE | 46.083 | 42246 → 42262 (+0.0%) | 1 / 0 | 16 | ĐẠT | ĐẠT |
| large | lecturer_whole_day | FEASIBLE | 43.597 | 42246 → 42246 (+0.0%) | 2 / 0 | 0 | ĐẠT | ĐẠT |
| large | three_simultaneous | FEASIBLE | 47.169 | 42246 → 42432 (+0.4%) | 2 / 0 | 83 | ĐẠT | ĐẠT |

Kết luận xếp lại trên large: đạt KPI dưới 60 giây trên cả ba kịch bản đã đo; giữ được chất lượng lịch ở cả ba kịch bản.

Giới hạn: mỗi cấu hình solver được đo với ba seed; mỗi kịch bản xếp lại chỉ đo một lần. Kết quả phụ thuộc môi trường máy và dữ liệu thực nghiệm.
<!-- EXPERIMENT_RESULTS_END -->

## 6. Đánh giá và kết luận

### 6.1. `two_phase` so với `single`

Trên `medium` và `large`, cùng seed thì `two_phase` luôn cho Z thấp hơn `single`:

| Bộ dữ liệu | Seed 0 | Seed 1 | Seed 2 | Z TB |
|---|---|---|---|---|
| `medium` (`single` / `two_phase`) | 13609 / 12268 | 16251 / 14231 | 15124 / 12652 | thấp hơn 13% |
| `large` (`single` / `two_phase`) | 46318 / 37660 | 42214 / 40018 | 41950 / 38596 | thấp hơn 11% |

Số sinh viên thi nhiều môn trong một ngày cũng ít hơn: 2–7 so với 17–23 trên `medium`, 38–54 so với 45–76 trên `large`.

`two_phase` đạt kết quả này dù chỉ dùng khoảng 241 trong 300 giây. Theo A.7, pha 1 được tối đa 80% thời gian, còn pha 2 (chỉ phân giám thị trên lịch đã cố định) xong trong vài giây, nên khoảng 60 giây còn lại không được dùng. Cho pha 1 dùng phần thời gian này là một hướng cải tiến.

Lý do `two_phase` tốt hơn: pha 1 không có biến giám thị nên mô hình nhỏ hơn nhiều, và không bị chậm bởi các lời giải tương đương sinh ra khi đổi chỗ các giám thị rảnh cùng lúc (A.7, A.13). Không lần chạy nào phải chuyển sang `single` (không có thông báo `S04`).

Trên dữ liệu nhỏ, `two_phase` chứng minh được tối ưu `toy` trong khoảng 4 giây, so với 12 giây của `single`. Trên `toy_gen`, `two_phase` cho cùng Z = 3650 với `single` nhưng chỉ là `FEASIBLE`: cận dưới của pha 1 là 3630 vì pha 1 bỏ A-S5, mà lịch tối ưu có A-S5 = 1 (trọng số 20), nên cận không bao giờ chạm 3650.

Trên `medium` và `large`, cận dưới của cả hai chiến lược đều âm, nên gap bằng 1: không lần nào chứng minh được gì về chất lượng lời giải. Vì vậy chỉ so sánh hai chiến lược bằng Z, không bằng gap. Dao động giữa các seed khá lớn (`two_phase` trên `medium`: 12268–14231), nên số lần chạy cho mỗi tổ hợp không nên ít hơn 3.

### 6.2. CP-SAT so với PuLP/CBC

| Bộ dữ liệu | CP-SAT | PuLP/CBC |
|---|---|---|
| `toy` | Z = 2391, chứng minh tối ưu trong 4–14 giây | Z = 2391, chạy hết 300 giây, không chứng minh được tối ưu |
| `toy_gen` | Z = 3650, `single` chứng minh tối ưu trong 18–26 giây | Z = 3650, 3650, 3710; chạy hết 300 giây, không chứng minh được |
| `medium` | Lời giải hợp lệ trong 300 giây | Không tìm được lời giải nào (A.13) |

CBC tìm được lời giải tốt cho dữ liệu nhỏ, nhưng có lần trên `toy_gen` dừng ở 3710 thay vì 3650 (kém 1,6%). CBC không dùng seed, nên khác biệt giữa ba lần đo là do thời điểm dừng. Nguyên nhân CBC yếu hơn đã phân tích ở A.13: nới lỏng tuyến tính của mô hình cho cận dưới yếu nên nhánh và cận phải duyệt rất nhiều nút, CBC chạy một luồng; còn CP-SAT dùng 8 luồng, kết hợp lan truyền ràng buộc và học mệnh đề. PuLP/CBC chỉ có vai trò đối chứng: kiểm tra hai cài đặt độc lập của cùng một mô hình cho cùng giá trị tối ưu.

### 6.3. Chiến lược được chọn

- `medium` và `large`: dùng `two_phase`.
- Dữ liệu nhỏ: giữ `single`, vì chứng minh được tối ưu trong vài chục giây.

Mặc định trong `configs/default.json` vẫn là `single`: các kiểm thử dựa trên lời giải tối ưu của `toy` (2391) cần `single`, và người dùng chọn `two_phase` trong giao diện hoặc cấu hình khi chạy dữ liệu lớn.

### 6.4. Xếp lại khi có sự cố

Lần đo đầu tiên (máy của Khỏe, lịch nền `large` có Z = 37660) dùng cách xếp lại cũ: giải trên toàn lịch, chỉ dùng lịch cũ làm gợi ý. Cả 6 kịch bản đều dưới 60 giây, nhưng kịch bản ba sự cố cùng lúc trên `large` cho lịch gần như mới hoàn toàn: Z tăng từ 37660 lên 108280, 98 lượt thay đổi, 39 lượt dời ca, 999 trong 1000 sinh viên bị ảnh hưởng.

Vì vậy cách xếp lại được sửa thành hai bước (model_spec A.14):

1. Xếp lại cục bộ: chỉ mở lại các môn có lượt dùng phòng hoặc giám thị vừa báo bận, các môn khác giữ nguyên như lịch cũ. Nếu vô nghiệm thì mở rộng sang các môn thi cùng ngày với sự cố, cuối cùng là toàn bộ lịch.
2. Với thời gian còn lại, giải trên toàn lịch với lời giải bước 1 làm gợi ý. Lời giải bước 2 chỉ được dùng khi tổng Z + chi phí thay đổi thấp hơn.

Bảng ở mục 5 là kết quả đo lại sau khi sửa, trên máy của Minh (Intel Core i7-1165G7, 8 luồng logic, 15,8 GB RAM, Python 3.12.10). Lịch nền được tạo lại bằng `two_phase` seed 0 trên máy này (`medium` Z = 12507, `large` Z = 42246), nên sự cố được chọn khác với lần đo đầu.

So sánh trên cùng lịch nền và cùng ba sự cố của `large` (phòng E3-LAB2 ca 1, phòng G2-103 ca 1, giảng viên GV01 cả ngày 14/12):

| Cách xếp lại | Lượt thay đổi (dời ca) | SV bị ảnh hưởng | Z | Tổng Z + chi phí thay đổi | Thời gian |
|---|---|---|---|---|---|
| Cũ: toàn lịch, gợi ý bằng lịch cũ | 77 (27) | 985 | 42246 → 59094 | 90894 | 46 giây |
| Mới, riêng bước 1 | 2 (0) | 83 | 42246 → 42432 | 42792 | 12 giây |

Bước 1 mở lại 2 trong 60 môn, nên mô hình còn rất ít biến tự do và CP-SAT chứng minh được tối ưu trong phạm vi đó. Trên `medium`, hai cách cho cùng một lịch (3 lượt thay đổi, 56 sinh viên), nhưng bước 1 xong trong 9,5 giây so với 38 giây của cách cũ. Trên `toy`, bước 2 tìm được lời giải tốt hơn lời giải cục bộ và chứng minh tối ưu, nên kết quả giống hệt cách cũ.

Sau khi sửa, cả 6 kịch bản đạt cả hai tiêu chí: 42–47 giây, Z tăng không quá 0,5%, 1–3 lượt thay đổi, không lượt nào bị dời ca. Ở cả 6 kịch bản, bước 2 không tìm được lời giải tốt hơn bước 1 trong thời gian còn lại. Tổng thời gian vẫn gần 45 giây vì bước 2 chạy hết phần thời gian còn lại, dù lời giải cuối cùng đã có sau 10–12 giây. Trạng thái được báo là `FEASIBLE`, vì lời giải cục bộ chỉ chứng minh tối ưu trong phạm vi đã mở lại.

Hướng cải tiến: trả lời giải bước 1 cho người dùng ngay, rồi để bước 2 chạy tiếp và chỉ thông báo khi tìm được lịch tốt hơn.

### 6.5. Giới hạn

`perf.csv` được đo trên máy của Khỏe (mục 4), `reschedule.csv` trên máy của Minh (mục 6.4); mỗi kịch bản xếp lại chỉ chạy một lần. Vì vậy chúng phản ánh hiệu năng của các lần chạy đã đo, không phải bảo đảm cho mọi dữ liệu và môi trường triển khai.

## 7. Độ nhạy trọng số (MINH-4)

Mục đích: trả lời câu hỏi thứ 5 của Daskin cho bài toán A, tức là lời giải thay đổi thế nào khi các trọng số và tham số thay đổi. Cụ thể có ba câu hỏi:

1. Trọng số nào làm lịch thay đổi nhiều nhất?
2. Thêm hoặc bớt một lượt thi (A-S6) thì sinh viên được hoặc mất bao nhiêu?
3. Trọng số mặc định trong `configs/default.json` có hợp lý không?

### Cách chạy

Từ thư mục gốc của repo:

```
py -3.12 -m experiments.sensitivity                       # chạy tất cả 65 lần, khoảng 2 giờ 30 phút
py -3.12 -m experiments.sensitivity --only weight noise   # chỉ chạy một số thí nghiệm
py -3.12 -m experiments.sensitivity --dataset toy_gen     # chỉ chạy trên một bộ dữ liệu
py -3.12 -m experiments.sensitivity --list                # in các lần chạy còn thiếu, không chạy
```

Mỗi lần chạy ghi ngay một dòng vào `results/sensitivity.csv`. Chạy lại thì các lần đã có trong file được bỏ qua, nên bị ngắt giữa chừng chỉ cần chạy lại lệnh cũ. Script kiểm tra từng lịch: nếu có vi phạm ràng buộc cứng hoặc điểm phạt của solver không khớp với điểm tính lại từ lịch thì dừng ngay, không ghi số sai. Cả 65 lần chạy đều qua kiểm tra này.

Các cột của `results/sensitivity.csv`:

| Cột | Ý nghĩa |
|---|---|
| `experiment`, `parameter`, `value` | Thí nghiệm, trọng số hoặc tham số được đổi, giá trị đã dùng (với `weight` là hệ số nhân) |
| `dataset`, `strategy`, `seed` | Bộ dữ liệu, chiến lược giải, `random_seed` của CP-SAT |
| `status`, `objective` | Trạng thái và giá trị hàm mục tiêu |
| `A-S1` ... `A-S6` | Điểm phạt từng ràng buộc mềm (chưa nhân trọng số) |
| `students_multi_exam_day`, `avg_gap_days`, `proctor_load_range`, `num_sittings`, `seat_fill_rate` | KPI của lịch |
| `solve_time_sec` | Thời gian giải |
| `sittings_moved`, `students_affected`, `change_cost`, `A-R1` ... `A-R4` | Chỉ có ở thí nghiệm xếp lại: số lượt bị dời ca, số sinh viên bị ảnh hưởng, chi phí thay đổi và điểm phạt từng loại thay đổi |

Với thí nghiệm xếp lại, `objective` là tổng phạt mềm Z của lịch mới. Hàm mục tiêu khi xếp lại là Z cộng `change_cost` (model_spec A.14).

### Thiết kế

| Thí nghiệm | Bộ dữ liệu | Nội dung | Số lần |
|---|---|---|---|
| `noise` | toy_gen (3 seed), medium (3 seed) | Cấu hình mặc định, chỉ đổi seed | 6 |
| `weight` | toy_gen | Nhân từng trọng số A-S1..A-S6 với 0; 0,5; 2; 5 | 24 |
| `tradeoff` | toy_gen; medium (3 seed) | A-S6 = 0, 50, 100, 200, 400, 800 (toy_gen); 0, 200, 800, 1600 (medium) | 18 |
| `param` | toy_gen; medium (3 seed) | `forbid_own_course` = true; `proctors_per_room` = 3 | 8 |
| `time_limit` | medium (3 seed) | Giới hạn 900 giây thay vì 300 giây | 3 |
| `reschedule_weight` | toy | Sự cố phòng G2-LAB1 ngày 2026-12-15 ca 3; A-R1 = 200, 1000, 5000; A-R3 = 10, 50, 200 | 6 |

Lý do chọn bộ dữ liệu, rút ra từ các lần chạy thử:

- toy quá chật: chỉ có một phòng máy nên mọi cách xếp đều cần cùng số lượt thêm, và lịch gần như không phản ứng với trọng số. Bộ này chỉ dùng cho thí nghiệm xếp lại, vì đã có lịch tham chiếu.
- toy_gen giải được tối ưu (OPTIMAL) trong 5 đến 170 giây, nên mọi khác biệt giữa các cấu hình là do trọng số. Đây là bộ chính để đo độ nhạy.
- medium chỉ đạt FEASIBLE trong 300 giây (chiến lược two_phase), nên chỉ dùng để xem xu hướng.

Hệ số 0,5 được cài bằng cách giữ nguyên trọng số đang xét và nhân các trọng số khác với 2, vì CP-SAT chỉ nhận số nguyên (A-S4 = 1 không chia đôi được). Cách này cho cùng lời giải tối ưu, chỉ có `objective` lớn gấp đôi.

### Độ tin cậy của số liệu

Kiểm tra theo lý thuyết. Khi lời giải là tối ưu, tăng trọng số của một tiêu chí thì điểm phạt của tiêu chí đó không được tăng. Trên toy_gen, cả sáu trọng số đều thỏa điều này:

| Hệ số | 0 | 0,5 | 1 | 2 | 5 |
|---|---|---|---|---|---|
| Phạt A-S1 khi đổi trọng số A-S1 | 65 | 0 | 0 | 0 | 0 |
| Phạt A-S2 khi đổi trọng số A-S2 | 128 | 113 | 113 | 113 | 80 |
| Phạt A-S5 khi đổi trọng số A-S5 | 3 | 1 | 1 | 1 | 1 |
| Phạt A-S6 khi đổi trọng số A-S6 | 2 | 1 | 1 | 1 | 1 |

A-S3 luôn bằng 0 và A-S4 luôn bằng 40.

Kiểm tra theo seed:

- toy_gen: ba seed cho cùng một lịch (objective 3650), nên số liệu tin được hoàn toàn.
- medium: ở cấu hình mặc định, ba seed cho 12072, 11805 và 15291. Số sinh viên thi hai môn cùng ngày lần lượt là 7, 6 và 29. Ở các cấu hình khác, các seed lệch nhau 8% đến 35%. Có thêm bằng chứng là solver chưa tìm được tối ưu: lịch tìm được khi đặt A-S6 = 0, chấm lại theo trọng số mặc định, được 11972 điểm, tốt hơn lịch chạy với trọng số mặc định ở seed 0 (12072).
- Cho medium thêm thời gian không giúp gì:

  | Seed | 300 giây | 900 giây |
  |---|---|---|
  | 0 | 12072 | 12075 |
  | 1 | 11805 | 11082 |
  | 2 | 15291 | 15453 |

  Seed 2 vẫn kém dù có gấp ba thời gian. Vì vậy chất lượng phụ thuộc vào hướng tìm kiếm ban đầu nhiều hơn là vào thời gian. Giả thuyết, chưa kiểm chứng: pha 1 của two_phase chốt ngày thi sớm, và pha 2 không sửa được một cách chia ngày xấu. Chạy 3 seed, mỗi seed 5 phút, rồi lấy lịch tốt nhất (11805) cho kết quả tốt hơn chạy một seed trong 15 phút.

Lịch có nhiều tối ưu: ở thí nghiệm xếp lại, các lịch có cùng tổng điểm nhưng số sinh viên thi hai môn cùng ngày khác nhau, từ 3 đến 5. Vì vậy KPI chỉ được so sánh khi điểm phạt khác nhau.

Quy ước dùng số liệu: với toy_gen thì dùng số cụ thể. Với medium chỉ nêu xu hướng khi cả ba seed cùng chiều, và báo trung bình kèm khoảng dao động.

### Kết quả

#### Câu 1: trọng số nào nhạy nhất

Trên toy_gen (objective mặc định 3650, 6 lượt thi, không sinh viên nào thi hai môn cùng ngày):

| Trọng số | Đặt về 0 | Nhân 0,5 hoặc 2 | Nhân 5 |
|---|---|---|---|
| A-S1 (thi cùng ngày) | 47 sinh viên thi hai môn cùng ngày | không đổi | không đổi |
| A-S2 (giãn cách) | phạt A-S2 tăng từ 113 lên 128 | không đổi | 33 sinh viên bị dồn hai môn vào cùng ngày, A-S2 giảm còn 80 |
| A-S3 (chia phòng) | không đổi | không đổi | không đổi |
| A-S4 (chỗ trống) | không đổi | không đổi | không đổi |
| A-S5 (công bằng giám thị) | chênh lệch tải giám thị tăng từ 1 lên 3 | không đổi | không đổi |
| A-S6 (số lượt) | thêm 1 lượt (7 lượt), tỷ lệ lấp chỗ giảm từ 89% xuống 82% | không đổi | không đổi |

A-S1 và A-S2 là hai trọng số nhạy nhất, và chúng kéo nhau. Ví dụ một sinh viên thi ba môn vào ba ngày liên tiếp bị phạt A-S2 hai lần. Nếu dồn hai môn vào một ngày và bỏ trống ngày giữa thì A-S2 chỉ còn phạt một lần, nhưng A-S1 bị phạt thêm một lần. Lý thuyết dự đoán lịch bắt đầu dồn môn khi trọng số A-S2 lớn hơn A-S1 = 100. Thực nghiệm thấy lịch đổi giữa 60 (nhân 2) và 150 (nhân 5), khớp với dự đoán.

A-S3 và A-S4 không làm lịch thay đổi trên toy_gen, vì phòng đủ rộng để không phải chia lượt. Đây là giới hạn của dữ liệu, không có nghĩa là hai trọng số này thừa.

#### Câu 2: một lượt thi đổi được bao nhiêu cho sinh viên

Trên toy_gen, lượt thi thứ 7 chỉ giảm được 2 đơn vị A-S2 (60 điểm), nhưng làm tăng 30 chỗ trống (A-S4). Tính ra, mở thêm lượt chỉ có lợi khi trọng số A-S6 nhỏ hơn 30. Thực nghiệm khớp: A-S6 = 0 cho 7 lượt, còn A-S6 từ 50 đến 800 đều cho 6 lượt.

Trên medium (trung bình 3 seed, trong ngoặc là khoảng dao động):

| A-S6 | Số lượt | Phạt A-S2 | Sinh viên thi hai môn cùng ngày |
|---|---|---|---|
| 0 | 52 (52-52) | 252 (201-294) | 5 (2-9) |
| 200 (mặc định) | 51 (50-52) | 208 (193-224) | 14 (6-29) |
| 800 | 44 (37-48) | 367 (286-498) | 10 (5-20) |
| 1600 | 45 (42-47) | 350 (319-407) | 8 (2-19) |

Xu hướng mà cả ba seed cùng đồng ý: tăng A-S6 lên 800 trở lên thì bớt được 6 đến 7 lượt, đổi lại phạt A-S2 tăng khoảng 150. Mỗi lượt bớt đi tương ứng khoảng 20 đến 25 lần sinh viên phải thi hai môn trong hai ngày liền nhau. Con số này chỉ là ước lượng thô, vì điểm A-S6 = 0 không theo xu hướng (nhiều lượt hơn mà A-S2 lại cao hơn mặc định), do solver chưa đạt tối ưu. Số sinh viên thi hai môn cùng ngày dao động quá lớn giữa các seed nên không kết luận được.

#### Tham số

| Tham số (medium, 3 seed) | Số lượt | Phạt A-S2 | Sinh viên thi hai môn cùng ngày |
|---|---|---|---|
| Mặc định | 51 (50-52) | 208 (193-224) | 14 (6-29) |
| `proctors_per_room` = 3 | 49 (47-51) | 295 (262-327) | 34 (29-44) |
| `forbid_own_course` = true | 50 (49-52) | 232 (210-259) | 21 (9-28) |

Thêm giám thị thứ ba cho mỗi phòng làm giãn cách xấu đi rõ rệt: khoảng A-S2 tách hẳn khỏi khoảng mặc định. Nhiều khả năng là do mỗi phòng cần thêm giám thị, nên mỗi ca mở được ít phòng hơn và các môn phải trải ra sát nhau hơn. Cấm giảng viên coi thi môn mình dạy không cho khác biệt rõ, nên quy định này gần như không tốn chi phí. Trên toy_gen, cả hai tham số đều không làm lịch thay đổi.

#### Trọng số xếp lại

Sự cố trên toy buộc phải dời đúng 1 lượt (A-R1 = 1), nên A-R1 = 200, 1000 hay 5000 đều cho cùng lịch. Vai trò của A-R1 là ngăn dời ca khi không bắt buộc.

| A-R3 | Chi phí thay đổi | Sinh viên đổi lượt (A-R3) | Phạt A-S1 | Z |
|---|---|---|---|---|
| 10 | 1290 | 17 | 5 | 2601 |
| 50 (mặc định) | 1970 | 17 | 5 | 2601 |
| 200 | 3320 | 11 | 11 | 3021 |

Bớt được 6 sinh viên phải đổi lượt thì Z tăng 420 điểm, chủ yếu do thêm 6 cặp môn thi cùng ngày. Vì vậy ngưỡng đổi chiều nằm ở A-R3 khoảng 70. Mặc định 50 nằm dưới ngưỡng, nên solver ưu tiên giữ lịch tốt và chấp nhận chuyển sinh viên. Mặc định khá gần ngưỡng, và đây là lựa chọn của phòng đào tạo: ít xáo trộn hơn hay ít sinh viên thi cùng ngày hơn.

#### Câu 3: trọng số mặc định có hợp lý không

Có:

- Lịch vững với sai số trọng số: nhân bất kỳ trọng số nào với 0,5 hoặc 2 (12 lần chạy), lịch toy_gen vẫn giữ nguyên. Không cần chọn trọng số thật chính xác.
- Tỷ lệ A-S1 : A-S2 = 100 : 30 giữ đúng thứ tự ưu tiên "tránh thi cùng ngày trước, giãn cách sau", và còn xa ngưỡng đổi chiều 100 : 100.
- A-S6 = 200 nằm xa ngưỡng 30 trên toy_gen, nên không mở lượt thừa. Trường muốn gom ca mạnh hơn thì tăng A-S6, đổi lại sinh viên phải thi sát ngày hơn.
- A-R3 = 50 ưu tiên chất lượng lịch khi xếp lại.

Theo các bên liên quan: sinh viên chịu ảnh hưởng của A-S1, A-S2 và A-R3; giảng viên coi thi chịu ảnh hưởng của A-S5 và `proctors_per_room`; phòng đào tạo chịu ảnh hưởng của A-S6 (số lượt, số đề) và A-S4 (sử dụng phòng).

Quyết định: giữ nguyên toàn bộ trọng số mặc định. Kết quả không cho thấy cần đổi, và giữ nguyên thì lịch tham chiếu `tests/reference/toy_schedule.json` (objective 2391) cùng các kiểm thử dựa trên nó vẫn đúng.

### Giới hạn và hướng cải tiến

- Hàm mục tiêu là tổng có trọng số, nên chỉ thấy được các điểm lồi trên đường đánh đổi. Phương pháp ε-constraint (giới hạn số lượt rồi tối ưu phần còn lại) sẽ cho đường đánh đổi đầy đủ hơn.
- toy quá chật, toy_gen quá nhỏ để A-S3 và A-S4 có tác động. Cần dữ liệu có phòng chật hơn để đo hai trọng số này.
- medium chưa đạt tối ưu, các seed lệch nhau tới khoảng 30%, và tăng thời gian từ 300 lên 900 giây không cải thiện. Hướng cải tiến: chạy nhiều seed song song rồi lấy lịch tốt nhất, hoặc xem lại cách pha 1 của two_phase chia ngày.
- Có nhiều lịch cùng tổng điểm nhưng KPI khác nhau. Có thể thêm một tiêu chí phụ để chọn giữa chúng.
