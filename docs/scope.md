# Phạm vi đề tài

**Đề tài:** Hệ thống xếp lịch phòng thi và phòng máy học phần

> Tài liệu này trả lời câu hỏi "nhóm làm đến đâu". Mọi task trên Coreach phải nằm trong phạm vi này.
> Muốn thêm/bớt gì thì sửa tài liệu này trước (qua Pull Request), rồi mới tạo task.

---

## 1. Mục tiêu

Xây dựng một hệ thống dịch vụ xếp lịch cho phòng đào tạo của một khoa:

1. Nhận dữ liệu: phòng, học phần, sinh viên đăng ký, giảng viên, các ca/buổi.
2. Dùng mô hình quy hoạch nguyên tuyến tính (ILP) để tự động tạo:
   - Bài toán A, lịch thi cuối kỳ: môn nào thi ca nào, ở phòng nào, giám thị nào coi.
   - Bài toán B, lịch phòng học/phòng máy theo tuần: lớp học phần nào học phòng nào, buổi nào.
3. Lịch tạo ra không có xung đột (thỏa mọi ràng buộc cứng) và tốt nhất có thể theo các tiêu chí chất lượng dịch vụ (ràng buộc mềm).
4. Đánh giá hệ thống bằng các chỉ số chất lượng dịch vụ (KPI) và các công cụ của môn học (tối ưu hóa, hàng đợi, tồn kho, SOA, mô hình hộp trắng).

Thứ tự ưu tiên: bài toán A làm trước và phải hoàn chỉnh. Bài toán B làm sau, dùng lại dữ liệu và code của A.

## 2. Bối cảnh và các bên liên quan

| Bên liên quan | Vai trò | Họ cần gì từ hệ thống |
|---|---|---|
| Phòng đào tạo / giáo vụ khoa | Người vận hành dịch vụ | Tạo lịch nhanh, không xung đột, sửa lịch dễ khi có sự cố |
| Sinh viên | Khách hàng chính | Không trùng lịch thi, các môn thi cách xa nhau, biết lịch sớm |
| Giảng viên / giám thị | Nguồn lực + người dùng | Không bị xếp trùng, được tôn trọng lịch bận, chia đều buổi coi thi |
| Kỹ thuật viên phòng máy | Nguồn lực | Phòng máy không bị khai thác quá tải, có thời gian bảo trì |

## 3. Quy mô dữ liệu

Toàn bộ dùng dữ liệu giả lập, sinh bằng script, quy mô gần với một khoa thật. Ba mức:

| Bộ dữ liệu | Học phần | Phòng (trong đó phòng máy) | Sinh viên | Mục đích |
|---|---|---|---|---|
| `toy` | 5 | 3 (1) | ~50 | Kiểm thử, có đáp án tính tay, minh họa báo cáo |
| `medium` | 30 | 10 (3) | ~500 | Demo chính |
| `large` | 60 | 15 (4) | ~1.000 | Thử khả năng mở rộng, đo thời gian giải |

## 4. Giả định

### 4.1. Chung

- Phạm vi một khoa, một học kỳ. Không xét phòng dùng chung với khoa khác.
- Mỗi phòng có: sức chứa (ghế), sức chứa khi thi, có phải phòng máy không, số máy đang hoạt động.
- Dữ liệu đầu vào là file CSV; định dạng chi tiết ở `docs/data_schema.md`.
- Các ca không được dùng (ngày lễ, phòng bảo trì, giảng viên bận) được đánh dấu trong dữ liệu đầu vào.

### 4.2. Khung giờ ca

Lịch thi và lịch học dùng chung khung 4 ca mỗi ngày, mỗi ca dài 150 phút:

| Ca | Giờ | Buổi |
|---|---|---|
| 1 | 07:00 – 09:30 | Sáng |
| 2 | 09:40 – 12:10 | Sáng |
| 3 | 13:00 – 15:30 | Chiều |
| 4 | 15:40 – 18:10 | Chiều |

Giữa ca 1 và ca 2, giữa ca 3 và ca 4 có 10 phút nghỉ để sinh viên và giám thị di chuyển sang phòng khác. Giữa ca 2 và ca 3 là giờ nghỉ trưa.

### 4.3. Bài toán A, lịch thi

Thời gian và số ca:

- Đợt thi kéo dài 2 tuần, mỗi tuần 6 ngày (Thứ 2 – Thứ 7), mỗi ngày 4 ca → 48 ca.
- Trong 150 phút của một ca, thời gian làm bài tối đa là 120 phút. 30 phút còn lại dành cho gọi tên, phát đề và thu bài.
- Mỗi lượt thi (xem mục "Lượt thi" bên dưới) chiếm 1 hoặc 2 ca, tùy thời lượng làm bài của môn:

  | Thời lượng làm bài | Số ca chiếm | Cách xếp |
  |---|---|---|
  | Đến 120 phút | 1 ca | Bất kỳ ca nào |
  | Từ 121 đến 280 phút | 2 ca liên tiếp | Ca 1 + 2 (07:00 – 12:10) hoặc ca 3 + 4 (13:00 – 18:10) |
  | Trên 280 phút | Không hỗ trợ | Ngoài phạm vi, thực tế hầu như không có |

  Khung 2 ca dài 310 phút (gồm cả 10 phút nghỉ ở giữa), trừ 30 phút gọi tên và thu bài nên thời gian làm bài tối đa là 280 phút.
- Lượt thi chiếm 2 ca không được kéo qua giờ nghỉ trưa, tức là không xếp ca 2 + 3, và không kéo sang ngày hôm sau.
- Lượt thi chiếm 2 ca dùng cùng phòng và cùng giám thị trong suốt 2 ca.
- Sinh viên làm đủ thời gian thì nộp bài và ra về, không phải chờ hết ca. Tuy vậy trong mô hình, phòng và giám thị vẫn được tính là bận đến hết ca, vì môn khác chỉ được bắt đầu ở đầu ca.
- Một sinh viên được phép thi 2 môn ở 2 ca liền nhau (nhờ 10 phút nghỉ). Điều này không bị cấm, chỉ bị hạn chế qua ràng buộc mềm A-S1.

Môn thi và phòng thi:

- Nếu một học phần có nhiều lớp học phần thì tất cả các lớp được gộp lại thành một môn thi.
- Hình thức thi của mỗi môn đã biết trước: thi viết hoặc thi trên máy.
- Môn thi viết chỉ xếp vào phòng thường. Môn thi trên máy chỉ xếp vào phòng máy. Phòng máy chỉ dùng cho môn thi trên máy, không dùng cho thi viết.
- Sức chứa khi thi mặc định bằng 1/2 số ghế (giãn cách); với phòng máy bằng số máy đang hoạt động. Dữ liệu đầu vào có thể ghi đè giá trị mặc định cho từng phòng.
- Trong một lượt thi, một môn đông có thể chia ra nhiều phòng. Ngược lại, một phòng trong một ca chỉ dành cho một môn, không ghép hai môn chung phòng để tránh nhầm đề.

Lượt thi:

- Lượt thi là một lần tổ chức thi của một môn, ở một ca (hoặc 2 ca liền nhau với môn dài), dùng một đề riêng.
- Môn thi trên máy được phép chia thành nhiều lượt ở các ca khác nhau, vì số máy thường ít hơn số sinh viên.
- Môn thi viết mặc định chỉ có 1 lượt. Có thể cho phép chia lượt với từng môn thi viết nếu cần, bằng một cột đánh dấu trong dữ liệu đầu vào. Đây là tùy chọn, không bắt buộc.
- Số lượt tối đa của mỗi môn được quy định trong dữ liệu đầu vào.
- Mỗi sinh viên của môn thi đúng một lượt. Hệ thống quyết định sinh viên nào thi lượt nào.
- Mỗi lượt thêm một đề phải chuẩn bị, nên số lượt được hạn chế qua ràng buộc mềm A-S6.

Giám thị:

- Mỗi phòng thi cần 2 giám thị. Giám thị là giảng viên của khoa; mỗi giảng viên có danh sách ca bận.
- Giảng viên được coi thi bình thường, kể cả môn mình dạy. Có một tùy chọn để cấm giảng viên coi thi môn mình dạy (ràng buộc A-H10); mặc định tùy chọn này tắt.

### 4.4. Bài toán B, lịch phòng học/phòng máy

- Lịch lặp lại theo tuần: 6 ngày × 4 ca/ngày = 24 ca/tuần, theo khung giờ ở mục 4.2.
- Mỗi buổi học chiếm 1 ca.
- Mỗi lớp học phần có số buổi/tuần, sĩ số, có cần phòng máy hay không, giảng viên phụ trách.
- Giờ học lý thuyết và thực hành của cùng một học phần được tách thành các lớp riêng.
- Lịch học được xếp trước khi sinh viên đăng ký, nên không thể kiểm tra trùng lịch theo từng sinh viên. Thay vào đó, mỗi lớp được gắn với khóa và ngành; các lớp bắt buộc của cùng một khóa, cùng một ngành không được trùng ca (ràng buộc B-H7).

### 4.5. Khi không xếp được lịch

Với một số bộ dữ liệu, có thể không tồn tại lịch nào thỏa hết ràng buộc cứng. Hệ thống không được im lặng hoặc trả về lịch sai, mà phải:

1. Kiểm tra trước khi giải những lỗi dễ phát hiện, ví dụ: một môn chỉ được thi 1 lượt nhưng đông hơn tổng sức chứa của mọi phòng phù hợp; môn được chia lượt nhưng số lượt tối đa vẫn không đủ chỗ; số giảng viên không đủ để coi thi; tổng số ca không đủ cho số môn.
2. Nếu vẫn không có lời giải sau khi chạy solver, báo rõ trạng thái "không khả thi" kèm gợi ý nhóm ràng buộc gây ra (ví dụ thiếu phòng máy, thiếu giám thị).
3. Nếu solver hết thời gian giới hạn mà mới có lời giải khả thi chưa chắc tối ưu, vẫn trả về lời giải đó kèm trạng thái "khả thi, chưa chứng minh tối ưu".

## 5. Trong phạm vi / Ngoài phạm vi

| ✅ Trong phạm vi | ❌ Ngoài phạm vi |
|---|---|
| Mô hình ILP cho bài toán A và B | Đăng nhập, phân quyền người dùng |
| Xếp giám thị cho lịch thi | Cơ sở dữ liệu thật (dùng CSV/JSON) |
| Giải bằng OR-Tools CP-SAT | Dữ liệu thật của khoa |
| So sánh với PuLP/CBC (nếu kịp) | Kết nối hệ thống đào tạo thật của trường |
| Script sinh dữ liệu giả lập | Xếp lịch giảng dạy toàn trường |
| Hàm kiểm tra lời giải (validator) và tính KPI | Ứng dụng di động |
| Giao diện web demo (Streamlit): tải dữ liệu, chạy, xem lịch, xuất Excel | Gửi thông báo/email thật |
| Kịch bản sự cố: phòng hỏng, thêm lớp → xếp lại | Môn thi dài hơn 280 phút |
| Phân tích dịch vụ và đánh giá theo các chương của môn | Tối ưu hóa thời gian thực cho cả năm học |

## 6. Ràng buộc (tóm tắt)

Đặc tả toán học đầy đủ nằm ở `docs/model_spec.md`. Mã ràng buộc dùng chung trong code, báo cáo và trao đổi.

### 6.1. Bài toán A, lịch thi

| Mã | Loại | Nội dung |
|---|---|---|
| A-H1 | Cứng | Mỗi môn có từ 1 lượt đến số lượt tối đa cho phép (môn không được chia thì đúng 1 lượt); mỗi lượt chiếm 1 hoặc 2 ca theo mục 4.3 |
| A-H2 | Cứng | Không sinh viên nào có 2 lượt thi trùng ca |
| A-H3 | Cứng | Tổng sức chứa các phòng của một lượt ≥ số sinh viên được xếp vào lượt đó |
| A-H4 | Cứng | Mỗi phòng, mỗi ca chỉ dành cho tối đa 1 môn |
| A-H5 | Cứng | Môn thi trên máy chỉ xếp vào phòng máy; phòng máy chỉ dùng cho môn thi trên máy |
| A-H6 | Cứng | Không xếp vào ca phòng đã báo bận |
| A-H7 | Cứng | Mỗi phòng thi đang dùng có đủ 2 giám thị; lượt chiếm 2 ca giữ nguyên 2 giám thị đó suốt 2 ca |
| A-H8 | Cứng | Một giám thị không coi 2 phòng cùng ca, không bị xếp vào ca bận |
| A-H9 | Cứng | Mỗi sinh viên thi đúng một lượt của mỗi môn mình đăng ký |
| A-H10 | Cứng, tùy chọn | Giảng viên không coi thi môn mình dạy (mặc định tắt) |
| A-S1 | Mềm | Hạn chế sinh viên thi ≥ 2 môn trong một ngày |
| A-S2 | Mềm | Giãn cách các môn thi của cùng một sinh viên |
| A-S3 | Mềm | Hạn chế chia một môn ra quá nhiều phòng |
| A-S4 | Mềm | Hạn chế lãng phí chỗ (phòng quá to so với số SV) |
| A-S5 | Mềm | Chia đều số buổi coi thi giữa các giám thị |
| A-S6 | Mềm | Hạn chế số lượt thi của mỗi môn (mỗi lượt là thêm một đề) |

Với lượt thi chiếm 2 ca, các ràng buộc A-H2, A-H4, A-H6 và A-H8 áp dụng cho cả hai ca: phòng, sinh viên và giám thị đều bận suốt hai ca đó.

### 6.2. Bài toán B, lịch phòng học/phòng máy

| Mã | Loại | Nội dung |
|---|---|---|
| B-H1 | Cứng | Mỗi lớp được xếp đủ số buổi/tuần |
| B-H2 | Cứng | Mỗi phòng, mỗi ca tối đa 1 lớp |
| B-H3 | Cứng | Sĩ số ≤ sức chứa phòng (phòng máy: ≤ số máy) |
| B-H4 | Cứng | Lớp thực hành chỉ xếp vào phòng máy |
| B-H5 | Cứng | Giảng viên không dạy 2 lớp cùng ca, không xếp vào ca bận |
| B-H6 | Cứng | Không xếp vào ca phòng đã báo bận (bảo trì, sự kiện) |
| B-H7 | Cứng | Các lớp bắt buộc của cùng một khóa, cùng một ngành không trùng ca |
| B-S1 | Mềm | Hạn chế lãng phí chỗ |
| B-S2 | Mềm | Tôn trọng nguyện vọng giờ dạy của giảng viên |
| B-S3 | Mềm | Các buổi của cùng một lớp không nằm cùng ngày |
| B-S4 | Mềm | Giữ hệ số sử dụng phòng máy ≤ 85% để có dự phòng |

## 7. Chỉ số đánh giá (KPI)

| KPI | Ý nghĩa dịch vụ | Mục tiêu |
|---|---|---|
| Số vi phạm ràng buộc cứng | Lịch có dùng được không | = 0 |
| Số SV thi ≥ 2 môn/ngày | Trải nghiệm sinh viên | Càng nhỏ càng tốt |
| Khoảng cách TB giữa 2 môn thi liên tiếp của SV | Trải nghiệm sinh viên | Càng lớn càng tốt |
| Chênh lệch số buổi coi thi giữa các giám thị | Công bằng cho giảng viên | Càng nhỏ càng tốt |
| Tổng số lượt thi (số đề phải chuẩn bị) | Chi phí tổ chức thi | Càng nhỏ càng tốt |
| Hệ số sử dụng phòng / phòng máy (ρ) | Hiệu quả nguồn lực (Ch.3) | 60–85% |
| Tỷ lệ lấp đầy chỗ ngồi | Lãng phí tài nguyên (Ch.5) | Càng cao càng tốt |
| Thời gian tạo lịch | Năng suất dịch vụ | < 5 phút với bộ `large` |
| Thời gian xếp lại khi có sự cố | Khả năng phục hồi dịch vụ | < 1 phút |

## 8. Công nghệ

- Ngôn ngữ: Python 3.11+
- Bộ giải chính: Google OR-Tools (CP-SAT)
- Bộ giải đối chứng: PuLP + CBC
- Dữ liệu: pandas, CSV/JSON
- Giao diện: Streamlit
- Quản lý mã nguồn: GitHub (repo này)
- Quản lý công việc: Coreach

## 9. Sản phẩm bàn giao

1. Mã nguồn trên GitHub, chạy được theo hướng dẫn trong `README.md`.
2. Ba bộ dữ liệu `toy`, `medium`, `large` + script sinh dữ liệu.
3. Giao diện demo.
4. Báo cáo (phân tích dịch vụ, mô hình, thực nghiệm, đánh giá).
5. Slide thuyết trình + video demo dự phòng.
