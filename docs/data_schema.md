# Định dạng dữ liệu

Tài liệu này quy định dữ liệu đầu vào, file cấu hình và file kết quả của hệ thống. Đây là "hợp đồng" giữa các thành viên: script sinh dữ liệu phải ghi đúng định dạng này, `data_loader.py` và solver đọc đúng định dạng này, giao diện chỉ đọc file kết quả theo định dạng này.

Mục 1 đến 8 dành cho bài toán A (lịch thi). Mục 9 dành cho bài toán B (lịch phòng học/phòng máy theo tuần); bài toán B dùng lại các quy ước chung của bài toán A và không thay đổi những gì đã quy định cho A.

Mọi ký hiệu toán học ($\kappa_r$, $L_c$, ...) tham chiếu đến `docs/model_spec.md`.

---

## 1. Tổ chức thư mục

```
data/
└── <tên bộ dữ liệu>/          ví dụ: toy, medium, large
    ├── slots.csv              bắt buộc
    ├── rooms.csv              bắt buộc
    ├── courses.csv            bắt buộc
    ├── enrollments.csv        bắt buộc
    ├── lecturers.csv          bắt buộc
    ├── teaching.csv           tùy chọn (bắt buộc khi bật forbid_own_course)
    └── unavailability.csv     tùy chọn
configs/
└── default.json               cấu hình chạy
output/
└── <tên bộ dữ liệu>/
    ├── schedule.json          kết quả xếp lịch
    └── reschedule.json        kết quả xếp lại khi có sự cố (mục 7.6)
```

Một bộ dữ liệu là một thư mục chứa các file CSV ở trên. Tên file viết thường, đúng như trên.

## 2. Quy ước chung cho mọi file CSV

| Quy ước | Nội dung |
|---|---|
| Mã hóa | UTF-8, có hoặc không có BOM (Excel thường ghi kèm BOM) |
| Dấu phân cách | Dấu phẩy `,`. Bộ đọc cũng chấp nhận dấu chấm phẩy `;` (Excel trên máy cài tiếng Việt hay xuất ra dấu này) và báo cảnh báo D16 |
| Dòng tiêu đề | Bắt buộc, là dòng đầu tiên không trống. Tên cột phải đúng như tài liệu nhưng không phân biệt chữ hoa, chữ thường (`Date` được hiểu là `date`). Thứ tự cột không quan trọng |
| Cột thừa | Được phép, bị bỏ qua, báo cảnh báo D09 |
| Ô chứa dấu phẩy | Đặt trong ngoặc kép theo chuẩn CSV, ví dụ `"Toán rời rạc, nâng cao"` |
| Khoảng trắng | Bộ đọc cắt bỏ khoảng trắng ở đầu và cuối mỗi ô |
| Ô trống | Coi là "không có giá trị". Cột bắt buộc mà để trống là lỗi D03 |
| Dòng trống | Bị bỏ qua |
| Số nguyên | Chỉ gồm chữ số, có thể có dấu trừ ở đầu. Không có phần thập phân, không có dấu phân cách hàng nghìn |
| Ngày | Dạng `YYYY-MM-DD`, ví dụ `2026-12-14` |
| Giá trị đúng/sai | `1` hoặc `0` (riêng file cấu hình JSON dùng `true`/`false`) |

### 2.1. Mã định danh (ID)

Các cột kết thúc bằng `_id` là mã định danh và tuân theo quy tắc sau:

- Chỉ gồm chữ cái tiếng Anh không dấu, chữ số và ba ký tự `_` `-` `.`, dài 1 đến 50 ký tự. Vi phạm là lỗi D06. Lý do: ID được ghép vào các mã khác trong file kết quả (mục 7) và dùng làm tên trong code, nên không được chứa ký tự đặc biệt hay dấu tiếng Việt. Tên tiếng Việt đặt ở các cột `_name`.
- Phân biệt chữ hoa, chữ thường: `INT2204` và `int2204` là hai mã khác nhau.
- Luôn được đọc là chuỗi, không bao giờ là số. Ví dụ mã sinh viên `0123` phải giữ nguyên số 0 ở đầu. Khi dùng pandas, bắt buộc đọc với `dtype=str`.
- Mã phòng, mã môn, mã giảng viên, mã sinh viên là bốn không gian tên riêng. Một mã phòng trùng với một mã giảng viên không phải là lỗi.

## 3. Các file đầu vào

Mỗi bảng dưới đây liệt kê các cột của một file. Cột "Bắt buộc" có ba giá trị: Có, Không, hoặc điều kiện cụ thể.

### 3.1. `slots.csv`: các ca thi dùng được

Mỗi dòng là một ca có thể tổ chức thi. Ca nghỉ (ngày lễ, nghỉ nửa buổi) chỉ đơn giản là không có dòng tương ứng.

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `date` | Ngày | Có | Ngày thi. Không được là Chủ nhật (lỗi D07) |
| `period` | Số nguyên 1–4 | Có | Thứ tự ca trong ngày, theo khung giờ ở scope mục 4.2 |

Khóa: cặp (`date`, `period`) không được lặp (lỗi D04).

Ánh xạ sang mô hình:
- $T$ là tập các dòng; $k(t)$ là `period`.
- $D$ là tập các giá trị `date` khác nhau.
- $Q$ (cặp ngày liên tiếp) gồm các cặp $(d, d')$ cùng thuộc $D$ và $d'$ là ngày ngay sau $d$ theo lịch. Vì Chủ nhật không được là ngày thi, Thứ 7 và Thứ 2 tuần sau không bao giờ thành cặp liên tiếp.
- Giờ bắt đầu và kết thúc của mỗi ca không nằm trong dữ liệu mà cố định theo scope mục 4.2.

Số ngày và số ca không bị giới hạn ở 2 tuần × 48 ca. Bộ `toy` có thể chỉ dùng vài ngày.

Ví dụ:

```csv
date,period
2026-12-14,1
2026-12-14,2
2026-12-14,3
2026-12-14,4
2026-12-15,1
2026-12-15,3
2026-12-15,4
```

Ở ví dụ trên, ngày 15/12 không có ca 2. Vì vậy môn thi 2 ca không được bắt đầu ở ca 1 ngày 15/12 (theo định nghĩa $S_c$ trong spec).

### 3.2. `rooms.csv`: phòng

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `room_id` | ID | Có | Mã phòng, duy nhất |
| `room_name` | Chuỗi | Không | Tên hiển thị, ví dụ "Phòng 101 nhà G2" |
| `building` | Chuỗi | Không | Tòa nhà, chỉ để hiển thị |
| `room_type` | `normal` hoặc `lab` | Có | Phòng thường hoặc phòng máy |
| `seats` | Số nguyên ≥ 0 | Có với `normal`, trừ khi có `exam_capacity` | Số ghế |
| `num_computers` | Số nguyên ≥ 0 | Có với `lab` | Số máy đang hoạt động |
| `exam_capacity` | Số nguyên | Không | Ghi đè sức chứa khi thi |

Sức chứa khi thi $\kappa_r$ được tính như sau:

| Trường hợp | $\kappa_r$ |
|---|---|
| Có `exam_capacity` | Lấy đúng giá trị `exam_capacity` |
| `normal`, không có `exam_capacity` | $\lfloor$ `seats` × `written_capacity_ratio` $\rfloor$, tỷ lệ mặc định 0,5 (mục 6) |
| `lab`, không có `exam_capacity` | `num_computers` |

Các trường hợp đặc biệt:

| Trường hợp | Xử lý |
|---|---|
| Phòng `normal` thiếu cả `seats` lẫn `exam_capacity` | Lỗi D08 |
| Phòng `lab` thiếu `num_computers` | Lỗi D08 |
| Phòng `normal` có điền `num_computers` | Cảnh báo D14, bỏ qua cột này |
| `exam_capacity` lớn hơn `seats` (phòng thường) hoặc lớn hơn `num_computers` (phòng máy) | Cảnh báo D13, vẫn dùng `exam_capacity` |
| $\kappa_r \le 0$ sau khi tính | Cảnh báo P9, loại phòng khỏi mô hình |

Ví dụ:

```csv
room_id,room_name,building,room_type,seats,num_computers,exam_capacity
G2-101,Phòng 101,G2,normal,60,,
G2-102,Phòng 102,G2,normal,40,,
G2-LAB1,Phòng máy 1,G2,lab,,30,
G2-LAB2,Phòng máy 2,G2,lab,,28,25
```

Ở ví dụ trên: $\kappa$ của G2-101 là 30, G2-102 là 20, G2-LAB1 là 30, G2-LAB2 là 25 (ghi đè, có thể vì 3 máy cần để dự phòng).

### 3.3. `courses.csv`: môn thi

Mỗi dòng là một môn thi. Các lớp học phần của cùng một học phần phải được gộp sẵn thành một dòng.

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `course_id` | ID | Có | Mã môn, duy nhất |
| `course_name` | Chuỗi | Không | Tên môn |
| `exam_type` | `written` hoặc `computer` | Có | Thi viết hoặc thi trên máy |
| `duration_min` | Số nguyên > 0 | Có | Thời lượng làm bài $\tau_c$ (phút) |
| `max_sittings` | Số nguyên ≥ 1 | Không | Số lượt tối đa $L_c$ |

Giá trị mặc định của `max_sittings`:

| `exam_type` | Mặc định |
|---|---|
| `written` | 1 (không chia lượt) |
| `computer` | Theo `default_max_sittings_computer` trong cấu hình, mặc định 3 |

Môn thi viết có `max_sittings` ≥ 2 được phép chia lượt; bộ đọc ghi thông tin P7.

Số sinh viên $n_c$ không có cột riêng mà được đếm từ `enrollments.csv`. Lý do: tránh trường hợp con số trong `courses.csv` mâu thuẫn với danh sách đăng ký.

Các trường hợp đặc biệt:

| Trường hợp | Xử lý |
|---|---|
| `duration_min` > 280 | Lỗi P1 |
| `duration_min` ≤ 0 hoặc `max_sittings` ≤ 0 | Lỗi D03 |
| Môn không có sinh viên nào đăng ký | Cảnh báo P2, bỏ môn khỏi mô hình |
| Môn thi máy nhưng không còn phòng máy nào ($R_c = \emptyset$) | Lỗi P3 |
| Môn không còn ca bắt đầu hợp lệ ($S_c = \emptyset$), ví dụ môn 2 ca trong khi không ngày nào có đủ cặp ca 1–2 hoặc 3–4 | Lỗi P4 |
| $n_c > L_c \cdot \sum_{r \in R_c} \kappa_r$ | Lỗi P5 |

Ví dụ:

```csv
course_id,course_name,exam_type,duration_min,max_sittings
INT2204,Lập trình hướng đối tượng,written,90,
INT2211,Cơ sở dữ liệu,computer,60,
INT3306,Phát triển ứng dụng Web,computer,180,2
MAT1099,Toán rời rạc,written,120,
INT3505,Khoa học dịch vụ,written,60,2
```

Ở ví dụ trên: INT3306 thi 180 phút nên mỗi lượt chiếm 2 ca, tối đa 2 lượt. INT3505 là môn thi viết nhưng được phép chia 2 lượt.

### 3.4. `enrollments.csv`: sinh viên đăng ký môn

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `student_id` | ID | Có | Mã sinh viên |
| `course_id` | ID | Có | Mã môn, phải có trong `courses.csv` (lỗi D05 nếu không) |

Tập sinh viên $I$ là tập các `student_id` xuất hiện trong file này; không có file danh sách sinh viên riêng. Một cặp (`student_id`, `course_id`) lặp lại thì chỉ giữ một dòng và báo cảnh báo P8.

```csv
student_id,course_id
22020001,INT2204
22020001,INT2211
22020002,INT2204
```

### 3.5. `lecturers.csv`: giảng viên

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `lecturer_id` | ID | Có | Mã giảng viên, duy nhất |
| `lecturer_name` | Chuỗi | Không | Họ tên |
| `is_proctor` | `0` hoặc `1` | Không, mặc định `1` | `1` nếu tham gia coi thi đợt này |

Tập giám thị $G$ gồm những giảng viên có `is_proctor = 1`. Giảng viên bận gần hết đợt thi nên được đặt `is_proctor = 0`, nếu không mục tiêu công bằng A-S5 sẽ mất ý nghĩa (spec A.6).

Số giám thị nhỏ hơn số giám thị mỗi phòng ($\lvert G \rvert < \nu$) là lỗi P6.

```csv
lecturer_id,lecturer_name,is_proctor
GV01,Nguyễn Văn An,1
GV02,Trần Thị Bình,1
GV03,Lê Văn Cường,0
```

### 3.6. `teaching.csv`: giảng viên dạy môn nào (tùy chọn)

Chỉ dùng cho ràng buộc tùy chọn A-H10. Một giảng viên có thể dạy nhiều môn, một môn có thể có nhiều giảng viên.

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `lecturer_id` | ID | Có | Phải có trong `lecturers.csv` |
| `course_id` | ID | Có | Phải có trong `courses.csv` |

| Trường hợp | Xử lý |
|---|---|
| Thiếu file trong khi cấu hình bật `forbid_own_course` | Lỗi D11 |
| Thiếu file và `forbid_own_course` tắt | Bình thường, không báo gì |
| Có file nhưng `forbid_own_course` tắt | Vẫn đọc và kiểm tra hợp lệ, nhưng không dùng trong mô hình |
| Dòng lặp | Chỉ giữ một dòng, không báo |
| Tham chiếu giảng viên `is_proctor = 0` | Hợp lệ, không ảnh hưởng gì |

```csv
lecturer_id,course_id
GV01,INT2204
GV02,INT2211
GV02,INT3306
```

### 3.7. `unavailability.csv`: ca bận của phòng và giảng viên (tùy chọn)

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `resource_type` | `room` hoặc `lecturer` | Có | Loại đối tượng bận |
| `resource_id` | ID | Có | `room_id` hoặc `lecturer_id`, tùy `resource_type` |
| `date` | Ngày | Có | Ngày bận |
| `period` | Số nguyên 1–4 | Không | Ca bận. Để trống nghĩa là bận cả ngày |
| `note` | Chuỗi | Không | Lý do, chỉ để hiển thị |

Ánh xạ sang mô hình: dòng `room` tạo phần tử của $B^{R}_r$; dòng `lecturer` tạo phần tử của $B^{G}_g$.

| Trường hợp | Xử lý |
|---|---|
| `resource_id` không tồn tại trong file tương ứng | Lỗi D05 |
| Ngày hoặc ca không có trong `slots.csv` | Cảnh báo D10, bỏ qua dòng đó (ca đó vốn không dùng để thi) |
| Dòng lặp, hoặc một dòng cả ngày trùng với dòng từng ca | Gộp lại, không báo |
| Giảng viên `is_proctor = 0` có ca bận | Hợp lệ, không ảnh hưởng gì |

```csv
resource_type,resource_id,date,period,note
room,G2-LAB1,2026-12-15,3,Bảo trì máy
lecturer,GV01,2026-12-14,,Đi công tác
lecturer,GV02,2026-12-16,1,
```

## 4. Bảng ánh xạ sang mô hình

| Ký hiệu trong spec | Lấy từ |
|---|---|
| $T$, $k(t)$, $D$, $Q$ | `slots.csv` |
| $R$, $R^{V}$, $R^{M}$ | `rooms.csv`, cột `room_type` (`normal` → $R^{V}$, `lab` → $R^{M}$), sau khi loại phòng P9 |
| $\kappa_r$ | `rooms.csv`, theo bảng tính ở mục 3.2 |
| $C$, $C^{V}$, $C^{M}$ | `courses.csv`, cột `exam_type` (`written` → $C^{V}$, `computer` → $C^{M}$), sau khi loại môn P2 |
| $\tau_c$, $\ell_c$ | `courses.csv`, cột `duration_min` |
| $L_c$ | `courses.csv`, cột `max_sittings` hoặc giá trị mặc định |
| $C^{P}$, $C^{U}$ | Suy ra từ $L_c$ |
| $I$, $I_c$, $C_i$, $n_c$ | `enrollments.csv` |
| $G$ | `lecturers.csv`, những dòng `is_proctor = 1` |
| $\Phi_g$ | `teaching.csv` |
| $B^{R}_r$, $B^{G}_g$ | `unavailability.csv` |
| $\nu$, $\theta$, $\omega_1..\omega_6$ | `config.json` |

## 5. Mã thông báo khi đọc dữ liệu

Bộ đọc dữ liệu không dừng ở lỗi đầu tiên mà kiểm tra hết, rồi trả về toàn bộ danh sách thông báo. Có ba mức:

- `error`: dừng, không chạy solver.
- `warning`: tự xử lý theo quy tắc (bỏ dòng, bỏ phòng...) rồi chạy tiếp.
- `info`: chỉ để biết.

Mã D là lỗi định dạng dữ liệu (tài liệu này). Mã P là kiểm tra trước khi giải (spec A.8). Mã R là thông báo của bước hậu xử lý sau khi giải. Mã S là thông báo của solver. Mã N là chẩn đoán nguyên nhân khi vô nghiệm (spec A.8). Mã I là thông báo khi xếp lại có sự cố (spec A.14).

| Mã | Mức | Nội dung |
|---|---|---|
| D01 | error | Thiếu file bắt buộc hoặc không đọc được file |
| D02 | error | Thiếu cột bắt buộc hoặc tên cột bị trùng |
| D03 | error | Giá trị sai kiểu hoặc ngoài miền cho phép (ví dụ `period = 5`, `exam_type = oral`, số âm, cột bắt buộc để trống) |
| D04 | error | Trùng khóa (trùng `room_id`, `course_id`, `lecturer_id`, hoặc trùng cặp `date`, `period` trong `slots.csv`) |
| D05 | error | Tham chiếu tới mã không tồn tại |
| D06 | error | Mã định danh chứa ký tự không hợp lệ |
| D07 | error | Ngày thi là Chủ nhật |
| D08 | error | Phòng thiếu dữ liệu sức chứa theo loại phòng |
| D09 | warning | Cột không có trong tài liệu, bị bỏ qua |
| D10 | warning | Ca bận nằm ngoài lịch thi, bị bỏ qua |
| D11 | error | Bật `forbid_own_course` nhưng thiếu `teaching.csv` |
| D12 | error hoặc warning | Cấu hình sai: giá trị sai là error; khóa lạ là warning, bị bỏ qua |
| D13 | warning | `exam_capacity` lớn hơn số ghế hoặc số máy |
| D14 | warning | Phòng thường có điền `num_computers`, bị bỏ qua |
| D15 | error | Sau khi lọc không còn môn nào, phòng nào hoặc ca nào để xếp |
| D16 | warning | File dùng dấu chấm phẩy làm dấu phân cách |
| P1–P9 | theo spec A.8 | Kiểm tra trước khi giải |
| R01 | info | Hậu xử lý: một phòng của lượt thi không có sinh viên nào (mục 7.3) |
| S01 | warning | Solver không tự dừng ở giới hạn thời gian nên bị dừng cưỡng bức; trạng thái `UNKNOWN` |
| S02 | error | Bộ giải bên ngoài (CBC) thoát bất thường; trạng thái `UNKNOWN` |
| S03 | warning | Hết ngân sách khi dựng mô hình hoặc trước khi bắt đầu search; với A `two_phase` gồm dựng pha 1 và chuẩn bị pha 2 (phân giám thị), với B gồm dựng mô hình lịch tuần; PuLP hết ngân sách dựng mô hình cũng dùng mã này |
| S04 | warning | Pha 2 của `two_phase` không tìm được cách phân giám thị; giải lại bằng `single` trong phần thời gian còn lại (spec A.7) |
| S05 | info | `two_phase`: trạng thái của từng pha và tổng thời gian |
| N01 | warning | Chẩn đoán: bỏ một nhóm ràng buộc (giám thị, A-H2 hoặc A-H6) thì xếp được lịch; kèm gợi ý sửa dữ liệu. Có thể có nhiều N01 |
| N02 | warning | Chẩn đoán: không nhóm nào riêng lẻ đủ, nhưng bỏ cả ba nhóm thì xếp được lịch (nhiều nguyên nhân cùng lúc) |
| N03 | warning | Chẩn đoán: bỏ cả ba nhóm vẫn vô nghiệm; nguyên nhân ở phòng và số lượt (A-H1, A-H3, A-H4, A-H5) |
| N04 | info | Chẩn đoán: một lần thử hết giờ mà chưa kết luận được |
| N05 | info | Chẩn đoán: tổng thời gian chẩn đoán |
| I01 | error | Sự cố không hợp lệ: sai loại, mã phòng hoặc giảng viên không có trong dữ liệu, sai dạng ngày, ca ngoài 1–4 |
| I02 | warning | Sự cố không ảnh hưởng gì (ngày hoặc ca không có trong lịch thi, hoặc giảng viên không coi thi), bị bỏ qua |
| I03 | error | Không đọc được lịch cũ, lịch cũ không có lượt thi, hoặc lịch cũ không thuộc bộ dữ liệu này (khác môn, khác danh sách sinh viên, phòng hoặc ca lạ) |
| I04 | info hoặc warning | Xếp lại: phạm vi cục bộ đã dùng (số môn mở lại), các phạm vi phải mở rộng, và bước giải trên toàn lịch có tìm được lời giải tốt hơn không (spec A.14). Mức warning khi hết thời gian mà chưa có lời giải |

Mỗi thông báo có dạng (cũng là dạng xuất hiện trong file kết quả, mục 7):

```json
{"code": "D05", "level": "error", "file": "enrollments.csv", "line": 17,
 "message": "course_id 'INT9999' không có trong courses.csv"}
```

Quy tắc tránh lỗi dây chuyền:

- Trong cùng một dòng: ô có giá trị nhưng sai kiểu chỉ báo D03, không bị coi là ô trống. Ví dụ `seats = 40.5` báo D03, không báo thêm D08 "thiếu số ghế".
- Giữa các file: D05 chỉ được báo khi mã hoàn toàn không xuất hiện trong file được tham chiếu. Nếu mã có mặt nhưng dòng chứa nó bị lỗi khác (ví dụ một dòng của `courses.csv` có `duration_min` sai), chỉ báo lỗi của chính dòng đó; các dòng ở file khác tham chiếu tới mã này được bỏ qua mà không báo thêm.

`file` và `line` có thể là `null` nếu thông báo không gắn với một dòng cụ thể. `line` đếm cả dòng tiêu đề, tức dòng dữ liệu đầu tiên là dòng 2, để khớp với số dòng khi mở file bằng trình soạn thảo.

## 6. File cấu hình `config.json`

Mọi khóa đều có giá trị mặc định. File cấu hình có thể chỉ ghi những khóa muốn thay đổi; file rỗng `{}` nghĩa là dùng toàn bộ mặc định.

| Khóa | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `strategy` | `"single"` hoặc `"two_phase"` | `"single"` | Giải một lần hay hai pha (spec A.7) |
| `time_limit_sec` | Số dương | `300` | Giới hạn thời gian, tính cả thời gian dựng mô hình. Với `two_phase` là tổng thời gian cả hai pha, kể cả khi phải giải lại bằng `single` (S04). Solver PuLP + CBC có thể chạy quá giới hạn này một chút; nếu vượt hạn cứng (giới hạn cộng thêm 30 giây hoặc 20%, lấy số lớn hơn) thì bị dừng với thông báo S01 |
| `num_workers` | Số nguyên ≥ 1 | `8` | Số luồng CP-SAT. Không áp dụng cho CBC (CBC luôn chạy một luồng, xem `src/exam_solver_pulp.py`) |
| `random_seed` | Số nguyên ≥ 0 | `0` | Hạt giống ngẫu nhiên của CP-SAT, để chạy lại cho cùng kết quả |
| `proctors_per_room` | Số nguyên ≥ 1 | `2` | $\nu$ |
| `forbid_own_course` | `true` hoặc `false` | `false` | $\theta$, bật A-H10 |
| `written_capacity_ratio` | Số trong khoảng (0, 1] | `0.5` | Tỷ lệ sức chứa khi thi của phòng thường |
| `default_max_sittings_computer` | Số nguyên ≥ 1 | `3` | $L_c$ mặc định của môn thi máy |
| `weights` | Đối tượng | Xem dưới | Trọng số các ràng buộc mềm, số nguyên ≥ 0 |
| `reschedule` | Đối tượng | Xem dưới | Chỉ dùng khi xếp lại có sự cố (spec A.14): `time_limit_sec` là giới hạn thời gian xếp lại; `weights` là trọng số phạt thay đổi A-R1..A-R4, số nguyên ≥ 0 |

Trọng số mặc định (theo spec A.6). Khóa nào không ghi thì lấy mặc định của khóa đó:

```json
{
  "strategy": "single",
  "time_limit_sec": 300,
  "num_workers": 8,
  "random_seed": 0,
  "proctors_per_room": 2,
  "forbid_own_course": false,
  "written_capacity_ratio": 0.5,
  "default_max_sittings_computer": 3,
  "weights": {"A-S1": 100, "A-S2": 30, "A-S3": 50, "A-S4": 1, "A-S5": 20, "A-S6": 200},
  "reschedule": {
    "time_limit_sec": 45,
    "weights": {"A-R1": 1000, "A-R2": 100, "A-R3": 50, "A-R4": 20}
  }
}
```

Trọng số bằng 0 nghĩa là tắt ràng buộc mềm đó. Lưu ý: ngay cả khi CP-SAT trả về `OPTIMAL`, với trọng số bằng 0 thì lời giải có thể không đẹp ở tiêu chí bị tắt.

## 7. File kết quả `schedule.json`

### 7.1. Cấu trúc tổng thể

```json
{
  "meta": { ... },
  "status": "OPTIMAL",
  "objective": 2029,
  "best_bound": 2029,
  "solve_time_sec": 32.5,
  "penalties": {"A-S1": 2, "A-S2": 38, "A-S3": 1, "A-S4": 39, "A-S5": 0, "A-S6": 3},
  "kpi": { ... },
  "sittings": [ ... ],
  "messages": [ ... ],
  "violations": [ ... ]
}
```

| Trường | Kiểu | Mô tả |
|---|---|---|
| `meta` | Đối tượng | Thông tin lần chạy (mục 7.2) |
| `status` | Chuỗi | Một trong: `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `UNKNOWN`, `INPUT_ERROR` |
| `objective` | Số nguyên hoặc `null` | Giá trị $Z$. `null` nếu không có lời giải |
| `best_bound` | Số hoặc `null` | Cận dưới tốt nhất solver chứng minh được. Bằng `objective` khi `OPTIMAL` |
| `solve_time_sec` | Số | Thời gian giải, không tính thời gian đọc dữ liệu |
| `penalties` | Đối tượng hoặc `null` | Giá trị $P_1..P_6$ chưa nhân trọng số, khóa là mã ràng buộc mềm |
| `kpi` | Đối tượng hoặc `null` | Mục 7.4 |
| `sittings` | Mảng | Các lượt thi (mục 7.3). Mảng rỗng nếu không có lời giải |
| `messages` | Mảng | Mọi thông báo D, P và thông báo của solver (mục 5) |
| `violations` | Mảng | Vi phạm ràng buộc cứng do validator phát hiện. Phải rỗng với lời giải đúng |

Ý nghĩa các trạng thái:

| `status` | Khi nào | `sittings` |
|---|---|---|
| `OPTIMAL` | Lịch tối ưu theo hàm mục tiêu | Có |
| `FEASIBLE` | Lịch hợp lệ, chưa chứng minh tối ưu (hết thời gian) | Có |
| `INFEASIBLE` | Đã chứng minh không có lịch nào thỏa ràng buộc cứng | Rỗng |
| `UNKNOWN` | Hết thời gian mà chưa tìm được lịch hợp lệ nào | Rỗng |
| `INPUT_ERROR` | Dữ liệu có lỗi mức `error`, solver không chạy | Rỗng |

### 7.2. `meta`

```json
{
  "problem": "A",
  "dataset": "toy",
  "created_at": "2026-12-01T09:30:00+07:00",
  "solver": "OR-Tools CP-SAT 9.15",
  "strategy": "single",
  "config": { ... toàn bộ cấu hình đã áp dụng, kể cả các giá trị mặc định ... }
}
```

Ghi lại toàn bộ cấu hình đã áp dụng để có thể chạy lại cho cùng kết quả khi làm thực nghiệm.

### 7.3. `sittings`: các lượt thi

Mỗi phần tử là một lượt thi. Mảng được sắp xếp theo `date`, rồi `start_period`, rồi `course_id`.

```json
{
  "sitting_id": "INT3306@2026-12-15_1",
  "course_id": "INT3306",
  "course_name": "Phát triển ứng dụng Web",
  "exam_type": "computer",
  "date": "2026-12-15",
  "start_period": 1,
  "periods": [1, 2],
  "start_time": "07:00",
  "end_time": "12:10",
  "duration_min": 180,
  "num_students": 52,
  "rooms": [
    {
      "room_id": "G2-LAB1",
      "exam_capacity": 30,
      "num_students": 30,
      "students": ["22020001", "22020005", "..."],
      "proctors": ["GV02", "GV05"]
    },
    {
      "room_id": "G2-LAB2",
      "exam_capacity": 25,
      "num_students": 22,
      "students": ["..."],
      "proctors": ["GV01", "GV04"]
    }
  ]
}
```

| Trường | Mô tả |
|---|---|
| `sitting_id` | `<course_id>@<date>_<start_period>`. Duy nhất vì một môn không có hai lượt cùng ca bắt đầu |
| `periods` | Các ca lượt thi chiếm: `[k]` hoặc `[k, k+1]` |
| `start_time`, `end_time` | Giờ bắt đầu ca đầu và giờ kết thúc ca cuối, theo scope mục 4.2. Đây là khung giờ giữ phòng, không phải giờ sinh viên nộp bài |
| `num_students` | Số sinh viên của lượt |
| `rooms[].students` | Danh sách mã sinh viên ngồi phòng đó, sắp tăng dần |
| `rooms[].proctors` | Đúng `proctors_per_room` mã giảng viên, sắp tăng dần; với lượt 2 ca, giữ nguyên ở cả hai ca |

Quy tắc chia sinh viên vào phòng (spec A.10), để mọi lần chạy cho cùng kết quả: sắp các phòng của lượt theo `exam_capacity` giảm dần, nếu bằng nhau thì theo `room_id` tăng dần; sắp sinh viên theo `student_id` tăng dần (so sánh chuỗi); lấp đầy lần lượt từng phòng.

Hệ quả là phòng cuối cùng có thể ít sinh viên. Phòng có 0 sinh viên chỉ có thể xuất hiện khi các phòng còn lại của lượt đã đủ chỗ, tức là phòng đó thừa. Với lời giải `OPTIMAL` và trọng số A-S3 hoặc A-S4 lớn hơn 0, điều này không xảy ra, vì bỏ phòng thừa sẽ giảm điểm phạt. Nó vẫn có thể xảy ra khi trạng thái là `FEASIBLE` (hết thời gian), hoặc khi cả hai trọng số A-S3 và A-S4 bằng 0. Khi đó phòng vẫn được giữ trong kết quả với `num_students = 0` và vẫn có đủ giám thị, đúng với lời giải của mô hình; bước hậu xử lý ghi thêm thông báo R01 để người dùng biết.

### 7.4. `kpi`

Định nghĩa chính xác các KPI trong scope mục 7:

| Khóa | Định nghĩa |
|---|---|
| `hard_violations` | Số phần tử trong `violations` |
| `students_multi_exam_day` | Số sinh viên có ít nhất một ngày bắt đầu từ 2 lượt thi trở lên |
| `avg_gap_days` | Với mỗi sinh viên thi từ 2 lượt trở lên, tính trung bình khoảng cách (số ngày theo lịch) giữa các cặp lượt liên tiếp của sinh viên đó; sau đó lấy trung bình trên các sinh viên này, mỗi sinh viên có trọng số như nhau. Hai lượt cùng ngày có khoảng cách 0. `null` nếu không có sinh viên nào thi từ 2 lượt |
| `min_gap_days` | Khoảng cách nhỏ nhất theo cùng cách tính. `null` trong cùng trường hợp |
| `proctor_load_min`, `proctor_load_max` | Số ca coi thi ít nhất và nhiều nhất trong $G$ (lượt 2 ca tính là 2 ca) |
| `proctor_load_range` | `proctor_load_max − proctor_load_min` |
| `num_sittings` | Tổng số lượt thi, cũng là số đề phải chuẩn bị |
| `room_utilization_normal` | Số cặp (phòng thường, ca) đang dùng chia cho số cặp (phòng thường, ca) không bận. `null` nếu mẫu số bằng 0 |
| `room_utilization_lab` | Như trên, cho phòng máy |
| `seat_fill_rate` | Tổng (số sinh viên × số ca) chia cho tổng (sức chứa phòng được dùng × số ca), tính trên mọi lượt. `null` nếu không có lượt nào |
| `solve_time_sec` | Bằng `solve_time_sec` ở cấp trên |

Thời gian xếp lại khi có sự cố (KPI cuối trong scope) không nằm trong file kết quả, mà được đo trong phần thực nghiệm.

### 7.5. `violations`

Validator kiểm tra lời giải độc lập với solver (spec A.10) và ghi mỗi vi phạm thành một phần tử:

```json
{"code": "A-H2", "message": "Sinh viên 22020001 thi INT2204 và INT2211 cùng ca 1 ngày 2026-12-14",
 "refs": {"student_id": "22020001", "sitting_ids": ["INT2204@2026-12-14_1", "INT2211@2026-12-14_1"]}}
```

`code` là mã ràng buộc cứng trong scope. `refs` chứa các mã liên quan để giao diện có thể làm nổi bật.

Ngoài việc soát lịch trong file kết quả, validator còn soát phần giám thị trong lời giải gốc của solver trước khi gộp. Lý do: file kết quả chỉ ghi một danh sách giám thị cho mỗi phòng của một lượt, nên không thể hiện được hai lỗi "lượt 2 ca đổi giám thị giữa hai ca" và "giám thị được xếp vào phòng không có ai thi". Hai lỗi này được báo với mã A-H7.

### 7.6. Kết quả xếp lại khi có sự cố

Hàm `reschedule` trong `src/reschedule.py` (giao diện gọi hàm này) và lệnh `python -m src.reschedule` ghi file cùng cấu trúc với mục 7.1, mặc định vào `output/<tên bộ dữ liệu>/reschedule.json`, với các khác biệt sau:

- `objective` là $Z$ của lịch mới, chưa cộng điểm phạt thay đổi. `best_bound` luôn là `null`.
- `meta.strategy` luôn là `single`; `meta.config.time_limit_sec` bằng `reschedule.time_limit_sec`.
- Thêm hai trường `changes` và `reschedule`. Khi trạng thái là `INPUT_ERROR`, `INFEASIBLE` hoặc `UNKNOWN`, `changes` là mảng rỗng và `reschedule.summary` là `null`.

Sự cố truyền vào hàm có dạng:

```json
{"resource_type": "room", "resource_id": "G2-LAB1", "date": "2026-12-15", "period": 3}
```

`period` là 1–4, hoặc `null` nghĩa là cả ngày.

Trường `reschedule`:

```json
{
  "base_schedule": "toy_schedule.json",
  "incidents": [{"resource_type": "room", "resource_id": "G2-LAB1", "date": "2026-12-15", "period": 3}],
  "change_penalties": {"A-R1": 1, "A-R2": 0, "A-R3": 17, "A-R4": 6},
  "change_cost": 1970,
  "summary": {
    "sittings_changed": 6, "sittings_moved": 1, "sittings_room_changed": 0,
    "sittings_proctor_changed": 2, "sittings_removed": 0, "sittings_added": 0,
    "students_affected": 11, "proctors_affected": 3
  }
}
```

| Khóa | Mô tả |
|---|---|
| `base_schedule` | Tên file lịch cũ |
| `incidents` | Các sự cố đã áp dụng, đã chuẩn hóa |
| `change_penalties` | $R_1..R_4$ (spec A.14), chưa nhân trọng số |
| `change_cost` | $\sum_k \rho_k R_k$ |
| `summary` | Số lượt bị đổi theo từng loại; số sinh viên có ngày, ca hoặc phòng thi bị đổi; số giám thị có tập ca coi thi bị đổi |

Mỗi phần tử của `changes` là một lượt bị đổi:

```json
{
  "course_id": "INT3306",
  "kinds": ["time", "proctors"],
  "old": {"sitting_id": "INT3306@2026-12-15_3", "date": "2026-12-15", "start_period": 3,
          "rooms": ["G2-LAB1"], "proctors": {"G2-LAB1": ["GV01", "GV06"]}},
  "new": {"sitting_id": "INT3306@2026-12-14_1", "date": "2026-12-14", "start_period": 1,
          "rooms": ["G2-LAB1"], "proctors": {"G2-LAB1": ["GV04", "GV06"]}},
  "students_affected": 11
}
```

`kinds` gồm một hoặc nhiều giá trị: `time` (dời ca), `rooms` (đổi phòng), `proctors` (đổi giám thị), `students` (giữ ca và phòng nhưng đổi sinh viên giữa các phòng hoặc các lượt), `removed` (bỏ lượt, `new` là `null`), `added` (thêm lượt, `old` là `null`). Lượt không đổi gì không có trong `changes`.

Các lượt được ghép theo từng môn: trước hết ghép lượt cùng ca bắt đầu, phần còn lại ghép theo số sinh viên chung nhiều nhất. `students_affected` của một lượt đếm sinh viên của lượt cũ hoặc lượt mới có ngày, ca hoặc phòng thi bị đổi, nên một sinh viên chuyển giữa hai lượt có thể được đếm ở cả hai; con số không trùng lặp nằm ở `summary`. Hàm `diff_schedules(old, new)` trong `src/reschedule.py` so sánh hai file `schedule.json` bất kỳ theo đúng quy tắc này.

## 8. Những điều cố ý không quy định

- Không có file danh sách sinh viên riêng. Mọi thông tin cần về sinh viên ở bài toán A đều nằm trong `enrollments.csv`.
- Không có cột tên sinh viên. File kết quả chỉ chứa mã sinh viên.
- Không cho phép cấu hình giờ của từng ca, vì khung giờ đã chốt trong scope mục 4.2.
- Không quy định cách lưu lịch sử nhiều lần chạy; mỗi lần chạy ghi đè `output/<tên bộ dữ liệu>/schedule.json`. Phần thực nghiệm tự đặt tên file kết quả riêng.

## 9. Bài toán B: lịch phòng học/phòng máy theo tuần

Mục này quy định dữ liệu của bài toán B (spec mục B). Mọi quy ước chung ở mục 2 (mã hóa, dấu phân cách, ID, ô trống...) và cách báo thông báo ở mục 5 giữ nguyên. Những gì đã quy định cho bài toán A không thay đổi.

### 9.1. Tổ chức thư mục

```
data/
└── <tên bộ dữ liệu>/          ví dụ: toy_b, medium_b, large_b
    ├── week_slots.csv         bắt buộc
    ├── rooms.csv              bắt buộc, cùng định dạng mục 3.2
    ├── lecturers.csv          bắt buộc, cùng định dạng mục 3.5
    ├── classes.csv            bắt buộc
    ├── class_groups.csv       tùy chọn
    ├── week_unavailability.csv  tùy chọn
    └── preferences.csv        tùy chọn
output/
└── <tên bộ dữ liệu>/
    └── timetable.json         kết quả xếp lịch học
```

Bộ đọc biết đang giải bài toán nào nhờ khóa `problem` trong cấu hình (mục 9.8), không đoán theo tên file. Vì tên file của hai bài toán không trùng nhau (trừ `rooms.csv` và `lecturers.csv` dùng chung), một thư mục có thể chứa cả dữ liệu A lẫn dữ liệu B; khi đó hai bài toán dùng chung danh sách phòng và giảng viên.

### 9.2. `week_slots.csv`: các ca học dùng được trong tuần

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `weekday` | Số nguyên 2–7 | Có | Thứ trong tuần: 2 là Thứ 2, ..., 7 là Thứ 7. Không có Chủ nhật |
| `period` | Số nguyên 1–4 | Có | Ca trong ngày, theo khung giờ scope mục 4.2 |

Khóa: cặp (`weekday`, `period`) không được lặp (lỗi D04). `weekday` ngoài 2–7 là lỗi D03.

Ánh xạ sang mô hình: $T$ là tập các dòng; $W$ là tập các giá trị `weekday` khác nhau; $T_d$ là các dòng có `weekday` bằng $d$. Ca không dùng (ví dụ chiều Thứ 7 khoa không xếp lịch) chỉ đơn giản là không có dòng.

```csv
weekday,period
2,1
2,2
2,3
2,4
7,1
7,2
```

### 9.3. `rooms.csv` và `lecturers.csv`

Cùng định dạng mục 3.2 và 3.5, có thể dùng chung file với bài toán A. Khác biệt khi đọc cho bài toán B:

| File | Khác biệt |
|---|---|
| `rooms.csv` | Sức chứa khi học $\sigma_r$ là `seats` với phòng `normal`, `num_computers` với phòng `lab`. Cột `exam_capacity` và tỷ lệ `written_capacity_ratio` không dùng. Phòng `normal` thiếu `seats` là lỗi D08, kể cả khi có `exam_capacity`. Phòng có $\sigma_r = 0$ bị loại, cảnh báo P9 |
| `lecturers.csv` | Cột `is_proctor` không dùng. Giảng viên không dạy lớp nào vẫn hợp lệ, chỉ không xuất hiện trong mô hình |

### 9.4. `classes.csv`: lớp học phần

Mỗi dòng là một lớp học phần. Lý thuyết và thực hành của cùng một học phần là hai dòng riêng (scope mục 4.4).

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `class_id` | ID | Có | Mã lớp, duy nhất |
| `class_name` | Chuỗi | Không | Tên hiển thị |
| `course_id` | ID | Không | Mã học phần, chỉ để hiển thị và gom các lớp cùng học phần. Không bắt buộc có trong `courses.csv` |
| `needs_lab` | `0` hoặc `1` | Có | `1` nếu lớp phải học phòng máy ($K^{M}$), `0` nếu học phòng thường ($K^{V}$) |
| `size` | Số nguyên ≥ 1 | Có | Sĩ số dự kiến $n_k$ |
| `sessions_per_week` | Số nguyên ≥ 1 | Có | Số buổi mỗi tuần $h_k$; mỗi buổi chiếm 1 ca |
| `lecturer_id` | ID | Có | Giảng viên dạy lớp, phải có trong `lecturers.csv` (lỗi D05 nếu không) |

| Trường hợp | Xử lý |
|---|---|
| `size` hoặc `sessions_per_week` ≤ 0 | Lỗi D03 |
| Không phòng nào đúng loại và đủ chỗ | Lỗi PB1 |
| `sessions_per_week` lớn hơn số ngày trong `week_slots.csv` | Thông tin PB6 |

```csv
class_id,class_name,course_id,needs_lab,size,sessions_per_week,lecturer_id
INT2204-LT,Lập trình hướng đối tượng (lý thuyết),INT2204,0,80,2,GV01
INT2204-TH1,Lập trình hướng đối tượng (thực hành 1),INT2204,1,30,1,GV04
INT2204-TH2,Lập trình hướng đối tượng (thực hành 2),INT2204,1,30,1,GV04
INT2211-LT,Cơ sở dữ liệu (lý thuyết),INT2211,0,60,2,GV02
```

### 9.5. `class_groups.csv`: lớp bắt buộc của từng nhóm sinh viên (tùy chọn)

Mỗi dòng nói lớp `class_id` là lớp bắt buộc của nhóm `group_id`. Một lớp có thể bắt buộc với nhiều nhóm (ví dụ môn chung của hai ngành), một nhóm có nhiều lớp bắt buộc. Lớp không có dòng nào là lớp tự chọn.

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `class_id` | ID | Có | Phải có trong `classes.csv` |
| `group_id` | ID | Có | Mã nhóm, ghép khóa và ngành, ví dụ `K67-CN`. Nhóm đông phải tách lớp thì mỗi phần là một nhóm riêng, ví dụ `K67-CN1` (spec B.2) |

Ánh xạ: $H$ là tập các `group_id`; $K_h$ là các `class_id` cùng `group_id` $h$. Không có file thì $H = \emptyset$ và B-H7 không có ràng buộc nào. Dòng lặp chỉ giữ một dòng, không báo.

```csv
class_id,group_id
INT2204-LT,K67-CN1
INT2204-LT,K67-CN2
INT2204-TH1,K67-CN1
INT2204-TH2,K67-CN2
INT2211-LT,K67-CN1
INT2211-LT,K67-CN2
INT2211-LT,K67-KHMT
```

Ở ví dụ trên, khóa K67 ngành CN được tách làm hai nhóm K67-CN1 và K67-CN2 vì lớp thực hành chỉ chứa được một nửa. Hai nhóm học chung lớp lý thuyết INT2204-LT, mỗi nhóm học một lớp thực hành riêng. Kết quả: INT2204-TH1 và INT2204-TH2 được phép trùng ca với nhau (khác nhóm), nhưng không lớp nào được trùng ca với INT2204-LT hay INT2211-LT. INT2211-LT còn là lớp bắt buộc của ngành KHMT.

Một khóa của một ngành chỉ dùng một cách chia nhóm: hoặc một nhóm `K67-CN`, hoặc các nhóm `K67-CN1`, `K67-CN2`, không dùng lẫn cả hai. Bộ đọc không tự suy ra quan hệ giữa các mã nhóm, nên bộ sinh dữ liệu phải ghi lớp chung cho từng nhóm như ví dụ.

### 9.6. `week_unavailability.csv`: ca bận trong tuần (tùy chọn)

Giống mục 3.7 nhưng theo thứ trong tuần thay vì ngày cụ thể. Ca bận lặp lại mọi tuần.

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `resource_type` | `room` hoặc `lecturer` | Có | Loại đối tượng bận |
| `resource_id` | ID | Có | `room_id` hoặc `lecturer_id` |
| `weekday` | Số nguyên 2–7 | Có | Thứ bận |
| `period` | Số nguyên 1–4 | Không | Ca bận. Để trống nghĩa là bận cả ngày |
| `note` | Chuỗi | Không | Lý do, chỉ để hiển thị |

Ánh xạ: dòng `room` tạo phần tử của $B^{R}_r$; dòng `lecturer` tạo phần tử của $B^{G}_g$. Các trường hợp đặc biệt xử lý như mục 3.7 (D05, D10, gộp dòng lặp).

```csv
resource_type,resource_id,weekday,period,note
room,G2-LAB1,6,4,Bảo trì định kỳ
lecturer,GV01,3,,Họp bộ môn
```

### 9.7. `preferences.csv`: ca giảng viên không muốn dạy (tùy chọn)

Mỗi dòng là một ca giảng viên không muốn dạy (B-S2). Khác ca bận ở mục 9.6: ca bận là cấm tuyệt đối, ca không muốn dạy chỉ bị phạt khi xếp vào.

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `lecturer_id` | ID | Có | Phải có trong `lecturers.csv` |
| `weekday` | Số nguyên 2–7 | Có | Thứ |
| `period` | Số nguyên 1–4 | Không | Ca. Để trống nghĩa là cả ngày |
| `note` | Chuỗi | Không | Chỉ để hiển thị |

Ánh xạ: tạo phần tử của $A_g$. Ca vừa có trong `preferences.csv` vừa bận trong `week_unavailability.csv` thì coi là bận, không báo. Ca không có trong `week_slots.csv` báo cảnh báo D10 và bị bỏ qua.

Chỉ ghi nhận ca không muốn dạy, không ghi ca muốn dạy. Lý do: một danh sách "không muốn" đủ để viết thành điểm phạt tuyến tính; danh sách "muốn" chỉ là phần bù của nó.

```csv
lecturer_id,weekday,period,note
GV01,7,,Không dạy Thứ 7
GV02,2,1,
```

### 9.8. Cấu hình

Thêm các khóa sau vào `config.json` (mục 6). Bài toán A bỏ qua các khóa của B và ngược lại.

| Khóa | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `problem` | `"A"` hoặc `"B"` | `"A"` | Bài toán cần giải |
| `lab_reserve_ratio` | Số trong khoảng (0, 1] | `0.85` | $\rho$ của B-S4 |
| `weights` | Đối tượng | | Thêm các khóa `B-S1` đến `B-S4`, mặc định `{"B-S1": 1, "B-S2": 50, "B-S3": 100, "B-S4": 30}` (spec B.6) |
| `reschedule.weights` | Đối tượng | | Thêm `B-R1`, `B-R2`, mặc định `{"B-R1": 100, "B-R2": 20}` (spec B.9) |

Với bài toán B, `strategy` luôn là `single`; cấu hình `two_phase` là lỗi D12. Các khóa `proctors_per_room`, `forbid_own_course`, `written_capacity_ratio`, `default_max_sittings_computer` không dùng.

### 9.9. Bảng ánh xạ sang mô hình

| Ký hiệu trong spec | Lấy từ |
|---|---|
| $T$, $W$, $T_d$ | `week_slots.csv` |
| $R$, $R^{V}$, $R^{M}$, $\sigma_r$ | `rooms.csv`, theo mục 9.3 |
| $K$, $K^{M}$, $K^{V}$, $n_k$, $h_k$, $g(k)$ | `classes.csv` |
| $G$, $K_g$ | Các `lecturer_id` xuất hiện trong `classes.csv` |
| $H$, $K_h$ | `class_groups.csv` |
| $B^{R}_r$, $B^{G}_g$ | `week_unavailability.csv` |
| $A_g$ | `preferences.csv` |
| $\rho$, $\beta_1..\beta_4$, $\gamma_1, \gamma_2$ | `config.json` |

### 9.10. Mã thông báo

Dùng lại toàn bộ mã D, S, N, I ở mục 5 với cùng ý nghĩa; thông báo ghi đúng tên file của bài toán B. Mã P của bài toán A không dùng, trừ P9 (phòng có sức chứa 0). Thêm các mã kiểm tra trước khi giải của bài toán B:

| Mã | Mức | Nội dung |
|---|---|---|
| PB1 | error | Lớp không có phòng nào đúng loại và đủ chỗ |
| PB2 | error | Lớp có ít ca dùng được hơn số buổi mỗi tuần (sau khi trừ ca bận của giảng viên và của mọi phòng phù hợp) |
| PB3 | error | Giảng viên dạy nhiều buổi hơn số ca rảnh trong tuần |
| PB4 | error | Nhóm sinh viên có nhiều buổi bắt buộc hơn số ca trong tuần |
| PB5 | error | Tổng số buổi cần phòng máy (hoặc phòng thường) lớn hơn tổng số cặp (phòng, ca) không bận của loại đó |
| PB6 | info | Lớp có số buổi mỗi tuần lớn hơn số ngày học, B-S3 không thể bằng 0 |
| PB7 | warning | Hệ số sử dụng phòng máy cả tuần lớn hơn `lab_reserve_ratio`, không thể chừa phòng máy dự phòng ở mọi ca |

### 9.11. File kết quả `timetable.json`

Cùng cấu trúc tổng thể với mục 7.1, thay `sittings` bằng `sessions`:

```json
{
  "meta": {"problem": "B", "dataset": "toy_b", "created_at": "...", "solver": "OR-Tools CP-SAT 9.15",
           "strategy": "single", "config": { ... }},
  "status": "OPTIMAL",
  "objective": 412,
  "best_bound": 412,
  "solve_time_sec": 1.2,
  "penalties": {"B-S1": 262, "B-S2": 1, "B-S3": 0, "B-S4": 2},
  "kpi": { ... },
  "sessions": [ ... ],
  "messages": [ ... ],
  "violations": [ ... ]
}
```

Các trường `status`, `objective`, `best_bound`, `solve_time_sec`, `messages`, `violations` có cùng ý nghĩa như mục 7.1. `penalties` có các khóa `B-S1` đến `B-S4`. Các con số ở ví dụ chỉ minh họa định dạng.

Mỗi phần tử của `sessions` là một buổi học. Mảng sắp theo `weekday`, rồi `period`, rồi `room_id`.

```json
{
  "session_id": "INT2204-LT@T2_1",
  "class_id": "INT2204-LT",
  "class_name": "Lập trình hướng đối tượng (lý thuyết)",
  "course_id": "INT2204",
  "needs_lab": false,
  "weekday": 2,
  "period": 1,
  "start_time": "07:00",
  "end_time": "09:30",
  "room_id": "G2-101",
  "room_capacity": 90,
  "size": 80,
  "lecturer_id": "GV01",
  "groups": ["K67-CN1", "K67-CN2"]
}
```

| Trường | Mô tả |
|---|---|
| `session_id` | `<class_id>@T<weekday>_<period>`. Duy nhất vì một lớp không có hai buổi cùng ca |
| `room_capacity` | $\sigma_r$ |
| `groups` | Các nhóm có lớp này là lớp bắt buộc, sắp tăng dần. Mảng rỗng với lớp tự chọn |

`kpi` của bài toán B:

| Khóa | Định nghĩa |
|---|---|
| `hard_violations` | Số phần tử trong `violations` |
| `room_utilization_normal` | Số cặp (phòng thường, ca) đang dùng chia cho số cặp (phòng thường, ca) không bận. `null` nếu mẫu số bằng 0 |
| `room_utilization_lab` | Như trên, cho phòng máy. Đây là hệ số sử dụng phòng máy cả tuần, so với mục tiêu 60–85% ở scope mục 7 |
| `lab_peak_utilization` | Giá trị lớn nhất theo ca của (số phòng máy đang dùng / $m_t$), bỏ qua ca có $m_t = 0$ |
| `slots_without_lab_reserve` | Số ca có $v_t > 0$, tức không còn phòng máy dự phòng theo ngưỡng $\rho$ |
| `seat_fill_rate` | Tổng sĩ số chia cho tổng sức chứa, tính trên mọi buổi. `null` nếu không có buổi nào |
| `preference_violations` | Số buổi xếp vào ca giảng viên không muốn dạy, bằng $P^{B}_2$ |
| `classes_same_day` | Số lớp có ít nhất một ngày học từ 2 buổi trở lên |
| `group_max_sessions_per_day` | Số buổi bắt buộc nhiều nhất của một nhóm trong một ngày. `null` nếu không có nhóm |
| `solve_time_sec` | Bằng `solve_time_sec` ở cấp trên |

`violations` có cùng dạng mục 7.5, `code` là mã B-H1 đến B-H7, `refs` chứa `class_id`, `room_id`, `lecturer_id`, `group_id` hoặc `session_ids` tùy vi phạm.

Kết quả xếp lại khi có sự cố (spec B.9) do `src/reschedule_b.py` ghi vào `output/<tên bộ dữ liệu>/retimetable.json`, theo cùng quy tắc mục 7.6, với các khác biệt sau.

Sự cố có hai loại:

```json
{"resource_type": "room", "resource_id": "G2-LAB1", "weekday": 6, "period": 4}
{"type": "add_class", "class": {"class_id": "INT9999-TH", "class_name": "...", "course_id": "INT9999",
  "lecturer_id": "GV04", "size": 12, "sessions_per_week": 2, "needs_lab": true, "groups": ["K67-KHMT"]}}
```

Loại thứ nhất là một dòng của `week_unavailability.csv` (`period` là `null` nghĩa là cả ngày), có thể kèm `"type": "unavailability"`. Loại thứ hai thêm một lớp mới, các trường như một dòng của `classes.csv` cộng các nhóm bắt buộc. Cũng có thể thêm lớp thẳng vào `classes.csv`: lớp có trong dữ liệu mà không có trong lịch cũ được coi là lớp mới (thông tin I04). Sự cố sai báo I01, sự cố không ảnh hưởng báo I02, lịch cũ sai báo I03, lớp mới không có phòng phù hợp báo PB1.

Trường `reschedule`:

| Khóa | Mô tả |
|---|---|
| `base_timetable` | Tên file lịch cũ |
| `incidents` | Các sự cố đã áp dụng, đã chuẩn hóa |
| `change_penalties` | `B-R1` (buổi cũ bị dời ca), `B-R2` (buổi cũ giữ ca nhưng đổi phòng), chưa nhân trọng số |
| `change_cost` | $\gamma_1 R^{B}_1 + \gamma_2 R^{B}_2$ |
| `summary` | `sessions_moved`, `sessions_room_changed`, `sessions_added`, `sessions_removed`, `classes_affected`, `lecturers_affected` |

Mỗi phần tử của `changes` là một buổi bị đổi, có đúng một loại trong `kinds`: `time` (dời ca), `rooms` (giữ ca, đổi phòng), `added` (buổi mới, `old` là `null`) hoặc `removed` (bỏ buổi, `new` là `null`; chỉ xảy ra khi số buổi của lớp trong dữ liệu ít hơn lịch cũ):

```json
{"class_id": "INT3505-TH", "kinds": ["time"],
 "old": {"session_id": "INT3505-TH@T6_4", "weekday": 6, "period": 4, "room_id": "G2-LAB1"},
 "new": {"session_id": "INT3505-TH@T6_3", "weekday": 6, "period": 3, "room_id": "G2-LAB1"}}
```

Các buổi được ghép theo từng lớp: trước hết ghép buổi cùng ca, phần còn lại ghép theo thứ tự thời gian. Hàm `diff_timetables(old, new)` trong `src/reschedule_b.py` so sánh hai file `timetable.json` bất kỳ theo quy tắc này.

### 9.12. Bộ dữ liệu

| Bộ | Lớp | Phòng (phòng máy) | Nhóm | Mục đích |
|---|---|---|---|---|
| `toy_b` | 10 | 4 (2) | 3 | Viết tay, kiểm thử, có đáp án tham chiếu 355 (spec B.12, `data/toy_b/README.md`) |
| `medium_b` | khoảng 60 | 10 (3) | khoảng 8 | Demo |
| `large_b` | khoảng 120 | 15 (4) | khoảng 16 | Đo thời gian giải |

`medium_b` và `large_b` dùng chung phòng và giảng viên với `medium`, `large` của bài toán A để đúng tinh thần "dùng lại dữ liệu của A" (scope mục 1). Riêng `toy_b` thêm một phòng máy G2-LAB2 vào 3 phòng của `toy`: với 1 phòng máy, ngưỡng dự phòng mỗi ca là ⌊0,85 × 1⌋ = 0 nên B-S4 không kiểm thử được. Số lớp được ước lượng từ số học phần ở scope mục 3: mỗi học phần một lớp lý thuyết, học phần có thực hành thêm 1–2 lớp thực hành.
