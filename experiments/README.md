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

Mỗi kịch bản được đo một lần, tổng cộng 6 lần xếp lại. Việc xếp lại sử dụng `src.reschedule.reschedule`, với chiến lược `single` và giới hạn solver theo `configs/default.json` (hiện là 45 giây).

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

Thông tin máy được ghi tại `output/perf/machine.json` và cập nhật tự động vào đây sau khi chạy `experiments/update_report.py`.

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
| medium | room_one_period | OPTIMAL | 23.534 | 12268 → 12268 (+0.0%) | 1 / 0 | 25 | ĐẠT | ĐẠT |
| medium | lecturer_whole_day | OPTIMAL | 24.778 | 12268 → 12308 (+0.3%) | 2 / 0 | 0 | ĐẠT | ĐẠT |
| medium | three_simultaneous | OPTIMAL | 25.105 | 12268 → 12268 (+0.0%) | 6 / 0 | 64 | ĐẠT | ĐẠT |
| large | room_one_period | FEASIBLE | 46.144 | 37660 → 37688 (+0.1%) | 1 / 0 | 14 | ĐẠT | ĐẠT |
| large | lecturer_whole_day | FEASIBLE | 46.080 | 37660 → 37660 (+0.0%) | 3 / 0 | 0 | ĐẠT | ĐẠT |
| large | three_simultaneous | FEASIBLE | 46.193 | 37660 → 108280 (+187.5%) | 98 / 39 | 999 | ĐẠT | KHÔNG ĐẠT |

Kết luận xếp lại trên large: đạt KPI dưới 60 giây trên cả ba kịch bản đã đo; chưa giữ được chất lượng lịch ở `three_simultaneous`.

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

Thời gian: cả 6 kịch bản có lịch hợp lệ trong dưới 60 giây. `medium` mất 23–25 giây và đạt `OPTIMAL`. `large` mất khoảng 46 giây và chỉ đạt `FEASIBLE`: solver chạy hết giới hạn 45 giây của `reschedule.time_limit_sec`. Nghĩa là trên `large`, KPI dưới 60 giây được bảo đảm bằng giới hạn thời gian, không phải vì solver giải xong nhanh.

Chất lượng: 5/6 kịch bản giữ lịch gần lịch cũ: Z tăng không quá 0,3%, chỉ 1–6 lượt thay đổi, không lượt nào bị dời ca. Kịch bản ba sự cố cùng lúc trên `large` không đạt: Z tăng từ 37660 lên 108280 (+188%), 98 lượt thay đổi, 39 lượt dời ca và 999 trong 1000 sinh viên bị ảnh hưởng. Trên thực tế, gần như cả lịch bị xếp lại. Giả thuyết, chưa kiểm chứng: khi lịch cũ vi phạm nhiều ràng buộc cùng lúc, CP-SAT không sửa được từ gợi ý (hint) và trong 45 giây chỉ tìm được một lời giải xa lịch cũ.

Hướng xử lý: chỉ cho thay đổi các lượt liên quan đến sự cố (các lượt dùng phòng hoặc giám thị bị sự cố, hoặc cùng ngày với sự cố) và cố định phần còn lại. Mô hình khi đó nhỏ hơn nhiều; nếu vô nghiệm thì mới mở rộng phạm vi. Việc này cần sửa `src/reschedule.py` và đo lại kịch bản trên, nên để thành việc riêng.

### 6.5. Giới hạn

Các kết quả được đo trên một cấu hình máy, mỗi kịch bản xếp lại chỉ chạy một lần. Vì vậy chúng phản ánh hiệu năng của các lần chạy đã đo, không phải bảo đảm cho mọi dữ liệu và môi trường triển khai.
