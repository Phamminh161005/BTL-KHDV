# Định dạng dữ liệu

Tài liệu này quy định dữ liệu đầu vào, file cấu hình và file kết quả của hệ thống. Đây là "hợp đồng" giữa các thành viên: script sinh dữ liệu phải ghi đúng định dạng này, `data_loader.py` và solver đọc đúng định dạng này, giao diện chỉ đọc file kết quả theo định dạng này.

Phiên bản hiện tại dành cho bài toán A (lịch thi). Các file và cột riêng của bài toán B sẽ được bổ sung ở phiên bản sau (xem mục 9); những gì đã quy định ở đây sẽ được giữ nguyên.

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
    └── schedule.json          kết quả
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

Mã D là lỗi định dạng dữ liệu (tài liệu này). Mã P là kiểm tra trước khi giải (spec A.8). Mã R là thông báo của bước hậu xử lý sau khi giải. Mã S là thông báo của solver.

| Mã | Mức | Nội dung |
|---|---|---|
| D01 | error | Thiếu file bắt buộc |
| D02 | error | Thiếu cột bắt buộc |
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
| `time_limit_sec` | Số dương | `300` | Giới hạn thời gian. Với `two_phase` là tổng thời gian cả hai pha. Solver PuLP + CBC có thể chạy quá giới hạn này một chút; nếu vượt hạn cứng (giới hạn cộng thêm 30 giây hoặc 20%, lấy số lớn hơn) thì bị dừng với thông báo S01 |
| `num_workers` | Số nguyên ≥ 1 | `8` | Số luồng CP-SAT. Không áp dụng cho CBC (CBC luôn chạy một luồng, xem `src/exam_solver_pulp.py`) |
| `random_seed` | Số nguyên ≥ 0 | `0` | Hạt giống ngẫu nhiên của CP-SAT, để chạy lại cho cùng kết quả |
| `proctors_per_room` | Số nguyên ≥ 1 | `2` | $\nu$ |
| `forbid_own_course` | `true` hoặc `false` | `false` | $\theta$, bật A-H10 |
| `written_capacity_ratio` | Số trong khoảng (0, 1] | `0.5` | Tỷ lệ sức chứa khi thi của phòng thường |
| `default_max_sittings_computer` | Số nguyên ≥ 1 | `3` | $L_c$ mặc định của môn thi máy |
| `weights` | Đối tượng | Xem dưới | Trọng số các ràng buộc mềm, số nguyên ≥ 0 |

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
  "weights": {"A-S1": 100, "A-S2": 30, "A-S3": 50, "A-S4": 1, "A-S5": 20, "A-S6": 200}
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

## 8. Những điều cố ý không quy định

- Không có file danh sách sinh viên riêng. Mọi thông tin cần về sinh viên ở bài toán A đều nằm trong `enrollments.csv`.
- Không có cột tên sinh viên. File kết quả chỉ chứa mã sinh viên.
- Không cho phép cấu hình giờ của từng ca, vì khung giờ đã chốt trong scope mục 4.2.
- Không quy định cách lưu lịch sử nhiều lần chạy; mỗi lần chạy ghi đè `output/<tên bộ dữ liệu>/schedule.json`. Phần thực nghiệm tự đặt tên file kết quả riêng.

## 9. Sẽ bổ sung cho bài toán B

Dự kiến thêm, không thay đổi những gì đã có ở trên:

- File lớp học phần cho bài toán B: số buổi mỗi tuần, sĩ số, cần phòng máy hay không, giảng viên phụ trách, khóa và ngành, có phải môn bắt buộc không.
- File nguyện vọng giờ dạy của giảng viên (B-S2).
- Lịch tuần của bài toán B dùng lại khung 4 ca/ngày nhưng theo thứ trong tuần thay vì ngày cụ thể.
- Thêm `problem: "B"` trong `meta` và các khóa trọng số `B-S1` đến `B-S4` trong cấu hình.
