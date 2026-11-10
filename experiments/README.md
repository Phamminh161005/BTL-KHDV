# Thực nghiệm

## Độ nhạy trọng số (MINH-4)

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
