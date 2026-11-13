# Bộ dữ liệu toy_b

Bộ dữ liệu nhỏ, viết tay, dùng để kiểm thử bài toán B (lịch phòng học/phòng máy theo tuần) và minh họa trong báo cáo. Không ghi đè bằng dữ liệu sinh tự động. Định dạng theo `docs/data_schema.md` mục 9.

## Nội dung

| Thành phần | Chi tiết |
|---|---|
| Lịch tuần | Thứ 2 đến Thứ 7, 22 ca. Thứ 7 chỉ học buổi sáng (ca 1, 2) |
| Phòng | 3 phòng của bộ `toy` thêm G2-LAB2: G2-101 (60 ghế), G2-102 (40 ghế), G2-LAB1 (15 máy), G2-LAB2 (20 máy). Cần 2 phòng máy để ràng buộc dự phòng B-S4 có ý nghĩa: với 1 phòng máy, ngưỡng mỗi ca là ⌊0,85 × 1⌋ = 0 |
| Giảng viên | 7 người, cùng file với bộ `toy` |
| Nhóm sinh viên | K67-CN1, K67-CN2 (khóa K67 ngành CN tách đôi vì lớp thực hành), K67-KHMT |
| Ca bận | G2-101 bận Thứ 2 ca 1; G2-LAB2 bảo trì cả Thứ 6; GV01 bận cả Thứ 3; GV03 bận Thứ 2 ca 3, 4; GV05 bận Thứ 5, 6, 7; GV06 chỉ rảnh Thứ 6 |
| Không muốn dạy | GV01 cả Thứ 7; GV02 Thứ 2 ca 1; GV03 Thứ 4 ca 4; GV05 cả Thứ 2 |

## Các lớp và tình huống mỗi lớp kiểm thử

| Lớp | Phòng | Sĩ số | Buổi/tuần | Giảng viên | Tình huống |
|---|---|---|---|---|---|
| INT2204-LT | Thường | 55 | 2 | GV01 | Chỉ G2-101 đủ chỗ; lớp bắt buộc chung của K67-CN1 và K67-CN2 |
| INT2204-TH1 | Máy | 18 | 1 | GV04 | Chỉ G2-LAB2 đủ máy |
| INT2204-TH2 | Máy | 14 | 1 | GV04 | Cùng giảng viên với TH1 nên không trùng ca dù khác nhóm |
| INT2211-LT | Thường | 35 | 2 | GV02 | Bắt buộc với cả 3 nhóm |
| INT2211-TH | Máy | 15 | 2 | GV02 | |
| MAT1099 | Thường | 50 | 3 | GV03 | Chỉ G2-101 đủ chỗ, tranh phòng với INT2204-LT |
| INT3306-TH | Máy | 12 | 4 | GV05 | GV05 chỉ dạy được Thứ 2–4 và không muốn dạy Thứ 2: đánh đổi giữa B-S2 và B-S3 |
| INT3505 | Thường | 30 | 1 | GV06 | Lớp tự chọn |
| INT3505-TH | Máy | 15 | 1 | GV06 | Chỉ học được Thứ 6, khi chỉ còn 1 phòng máy: B-S4 không tránh được |
| ELT2035 | Thường | 40 | 7 | GV07 | Lớp học bù, nhiều buổi hơn số ngày: thông tin PB6, B-S3 không tránh được |

## Đáp án tham chiếu

Với trọng số mặc định (`B-S1` 1, `B-S2` 50, `B-S3` 100, `B-S4` 30, $\rho$ = 0,85), giá trị mục tiêu tối ưu là 355:

| B-S1 | B-S2 | B-S3 | B-S4 |
|---|---|---|---|
| 75 | 1 | 2 | 1 |

- B-S2 = 1 và một phần B-S3: INT3306-TH có 4 buổi nhưng chỉ có 3 ngày học được. Xếp 1 buổi vào Thứ 2 (ngày GV05 không muốn, phạt 50) rẻ hơn dồn 2 + 2 buổi vào Thứ 3, Thứ 4 (phạt thêm 100). Lịch tối ưu có dạng 1-2-1, tức một buổi thừa.
- B-S3 còn 1 buổi thừa nữa của ELT2035: 7 buổi trong 6 ngày.
- B-S4 = 1: buổi của INT3505-TH vào Thứ 6, hôm đó chỉ còn G2-LAB1.
- B-S1 = 75: tổng chỗ trống của 24 buổi học.

Lịch tối ưu có thể khác nhau giữa các lần chạy, nhưng giá trị mục tiêu tối ưu là duy nhất. Kết quả kiểm chứng: `docs/model_spec.md` mục B.12.

## Lịch tham chiếu và ý nghĩa KPI

`tests/reference/toy_timetable.json` là lịch tham chiếu 24 buổi: lấy đúng lịch tối ưu cố định trong `tests/test_validator_b.py`, dựng thành file kết quả bằng `src/timetable.py` (cùng hàm hậu xử lý mà `run.py` dùng), nên có đủ các trường theo data_schema mục 9.11. Validator không báo vi phạm, điểm phạt tính lại là B-S1..B-S4 = 75, 1, 2, 1. Trường `solve_time_sec` bằng 0 vì lịch được cố định sẵn, không đo thời gian giải. Mỗi lần chạy solver có thể ra một lịch tối ưu khác, nhưng giá trị mục tiêu luôn là 355.

| KPI | Ý nghĩa phục vụ |
|---|---|
| `hard_violations` | Số lỗi cứng; lịch chỉ có thể dùng khi bằng 0. |
| `room_utilization_normal` | Tỷ lệ cặp phòng thường-ca được dùng trên số cặp không bận, đo mức khai thác phòng thường. |
| `room_utilization_lab` | Tỷ lệ tương tự cho phòng máy, đối chiếu mục tiêu khai thác 60–85%. |
| `lab_peak_utilization` | Tỷ lệ phòng máy dùng cao nhất trong một ca có phòng khả dụng, nhận diện nút thắt. |
| `slots_without_lab_reserve` | Số ca dùng quá ngưỡng `floor(rho × số phòng máy không bận)`, cảnh báo thiếu dự phòng. |
| `seat_fill_rate` | Tổng sĩ số / tổng sức chứa của các buổi học, đo hiệu quả dùng chỗ. |
| `preference_violations` | Số buổi rơi vào ca giảng viên không muốn dạy (B-S2). |
| `classes_same_day` | Số lớp có ít nhất một ngày học hai buổi trở lên, đo độ dồn lịch. |
| `group_max_sessions_per_day` | Số buổi bắt buộc nhiều nhất của một nhóm trong một ngày, đo tải học cao nhất. |
| `solve_time_sec` | Thời gian giải do kết quả cung cấp; không bao gồm thời gian tính KPI. |

Tỷ lệ phòng trả `null` nếu không có cặp phòng-ca khả dụng; tỷ lệ đầy chỗ trả `null` khi không có buổi; đỉnh phòng máy trả `null` khi không có ca nào có phòng máy khả dụng; tải nhóm trả `null` nếu không có nhóm.
