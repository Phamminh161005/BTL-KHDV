# Đặc tả mô hình toán

Tài liệu này viết các quy tắc trong `docs/scope.md` thành mô hình quy hoạch nguyên tuyến tính (ILP). Code solver, validator và chương mô hình trong báo cáo đều phải bám đúng tài liệu này. Mỗi ràng buộc mang đúng mã đã đặt trong scope (A-H1, A-S1, ...).

Tài liệu gồm hai phần: bài toán A (lịch thi) và bài toán B (lịch phòng học/phòng máy theo tuần). Bài toán B trình bày theo cùng cách với bài toán A và dùng lại các quy ước của A khi có thể.


---

## A. Bài toán lịch thi

### A.1. Ý tưởng chính

Mô hình trả lời bốn câu hỏi:

1. Mỗi môn có những lượt thi nào, mỗi lượt bắt đầu ở ca nào?
2. Mỗi lượt dùng những phòng nào?
3. Với môn được chia lượt, mỗi sinh viên thi lượt nào?
4. Mỗi phòng đang thi ở mỗi ca do hai giám thị nào coi?

Một lượt thi được xác định bằng cặp (môn, ca bắt đầu). Nói cách khác, không đánh số "lượt 1, lượt 2" mà chỉ hỏi "môn $c$ có một lượt bắt đầu ở ca $s$ hay không". Cách này có ba lợi ích:

- Hai lượt của cùng một môn không thể trùng ca bắt đầu, nên không cần thêm ràng buộc để tách chúng.
- Không sinh ra các lời giải đối xứng kiểu "đổi tên lượt 1 thành lượt 2", giúp solver chạy nhanh hơn.
- Ràng buộc trùng lịch của sinh viên viết được dưới dạng tuyến tính mà không phải nhân hai biến với nhau (xem A.5, A-H2).

### A.2. Tập hợp và chỉ số

| Ký hiệu | Ý nghĩa |
|---|---|
| $D$ | Tập ngày thi (12 ngày: 2 tuần, Thứ 2 đến Thứ 7), chỉ số $d$ |
| $T$ | Tập các ca thi dùng được, chỉ số $t$ hoặc $s$. Các ca rơi vào ngày nghỉ của toàn khoa đã bị loại khỏi $T$ |
| $T_d \subseteq T$ | Các ca thuộc ngày $d$ |
| $k(t) \in \{1,2,3,4\}$ | Thứ tự của ca $t$ trong ngày |
| $t^{+}$ | Ca kế tiếp của $t$ trong cùng buổi: nếu $k(t)=1$ thì là ca 2 cùng ngày, nếu $k(t)=3$ thì là ca 4 cùng ngày; không định nghĩa với $k(t) \in \{2,4\}$ |
| $C$ | Tập môn thi, chỉ số $c$. Các lớp học phần của cùng một học phần đã được gộp thành một môn |
| $C^{V}, C^{M}$ | Môn thi viết, môn thi trên máy. $C = C^{V} \cup C^{M}$, hai tập không giao nhau |
| $C^{P}$ | Môn được phép chia lượt, tức $L_c \ge 2$ (xem tham số) |
| $C^{U}$ | Môn chỉ có một lượt, $C^{U} = C \setminus C^{P}$ |
| $R$ | Tập phòng, chỉ số $r$ |
| $R^{V}, R^{M}$ | Phòng thường, phòng máy. $R = R^{V} \cup R^{M}$, hai tập không giao nhau |
| $R_c$ | Phòng phù hợp với môn $c$: $R_c = R^{V}$ nếu $c \in C^{V}$, $R_c = R^{M}$ nếu $c \in C^{M}$ |
| $I$ | Tập sinh viên, chỉ số $i$ |
| $I_c$ | Sinh viên đăng ký môn $c$ |
| $C_i$ | Các môn sinh viên $i$ đăng ký |
| $G$ | Tập giảng viên tham gia coi thi, chỉ số $g$ |
| $Q$ | Tập cặp ngày thi $(d, d')$ với $d'$ là ngày ngay sau $d$ theo lịch, ví dụ Thứ 2–Thứ 3. Thứ 7 và Thứ 2 tuần sau không phải cặp vì có Chủ nhật ở giữa; tương tự nếu Thứ 4 nghỉ lễ thì Thứ 3 và Thứ 5 không phải cặp, vì sinh viên có ngày nghỉ ở giữa để ôn |

### A.3. Tham số (dữ liệu biết trước)

| Ký hiệu | Ý nghĩa | Ghi chú |
|---|---|---|
| $\tau_c$ | Thời lượng làm bài của môn $c$ (phút) | |
| $\ell_c \in \{1,2\}$ | Số ca mỗi lượt của môn $c$ chiếm | $\ell_c = 1$ nếu $\tau_c \le 120$; $\ell_c = 2$ nếu $120 < \tau_c \le 280$. Môn có $\tau_c > 280$ bị loại ở bước kiểm tra trước (A.8) |
| $L_c \ge 1$ | Số lượt tối đa của môn $c$ | Môn thi viết mặc định $L_c = 1$; chỉ lớn hơn 1 khi dữ liệu đánh dấu cho phép chia |
| $n_c$ | Số sinh viên của môn $c$, $n_c = \lvert I_c \rvert$ | |
| $\kappa_r$ | Sức chứa khi thi của phòng $r$ | Số nguyên. Mặc định $\lfloor$số ghế$/2\rfloor$ với phòng thường, bằng số máy đang hoạt động với phòng máy |
| $B^{R}_r \subseteq T$ | Các ca phòng $r$ bận | |
| $B^{G}_g \subseteq T$ | Các ca giảng viên $g$ bận | |
| $\Phi_g \subseteq C$ | Các môn giảng viên $g$ dạy | Chỉ dùng khi bật A-H10 |
| $\nu = 2$ | Số giám thị mỗi phòng | |
| $\theta \in \{0,1\}$ | Bật/tắt A-H10 | Mặc định $\theta = 0$ |
| $\omega_1, \dots, \omega_6$ | Trọng số các ràng buộc mềm | Số nguyên, xem A.6 |

Từ các tham số trên, định nghĩa thêm hai tập dẫn xuất:

- Tập ca được phép bắt đầu của môn $c$:

$$
S_c =
\begin{cases}
T & \text{nếu } \ell_c = 1 \\
\{\, s \in T : k(s) \in \{1,3\} \text{ và } s^{+} \in T \,\} & \text{nếu } \ell_c = 2
\end{cases}
$$

- Tập ca bị chiếm khi lượt của môn $c$ bắt đầu ở ca $s$:

$$
\mathrm{Cov}(c,s) =
\begin{cases}
\{s\} & \text{nếu } \ell_c = 1 \\
\{s, s^{+}\} & \text{nếu } \ell_c = 2
\end{cases}
$$

- Ngược lại, các ca bắt đầu của môn $c$ mà lượt đó đang diễn ra ở ca $t$:

$$
S_c(t) = \{\, s \in S_c : t \in \mathrm{Cov}(c,s) \,\}
$$

Ví dụ: môn 180 phút có $\ell_c = 2$. Nó chỉ được bắt đầu ở ca 1 hoặc ca 3. Nếu bắt đầu ở ca 1 ngày Thứ 2 thì chiếm ca 1 và ca 2 của ngày đó. Ở ca 2 ngày Thứ 2, $S_c(t)$ chứa đúng ca 1 ngày Thứ 2.

Điều kiện $s^{+} \in T$ đảm bảo lượt 2 ca không bắt đầu ở ca 1 nếu ca 2 cùng ngày đã bị loại (ngày nghỉ nửa buổi chẳng hạn), và không bao giờ vắt qua giờ nghỉ trưa hay sang ngày hôm sau.

### A.4. Biến quyết định

| Biến | Miền | Ý nghĩa |
|---|---|---|
| $x_{c,s}$ | $\{0,1\}$, với $c \in C,\ s \in S_c$ | Bằng 1 nếu môn $c$ có một lượt bắt đầu ở ca $s$ |
| $u_{c,r,s}$ | $\{0,1\}$, với $c \in C,\ r \in R_c,\ s \in S_c$ | Bằng 1 nếu lượt $(c,s)$ dùng phòng $r$ |
| $q_{i,c,s}$ | $\{0,1\}$, với $c \in C^{P},\ i \in I_c,\ s \in S_c$ | Bằng 1 nếu sinh viên $i$ thi môn $c$ ở lượt bắt đầu ca $s$. Chỉ tồn tại với môn được chia lượt |
| $w_{g,r,t}$ | $\{0,1\}$, với $g \in G,\ r \in R,\ t \in T$ | Bằng 1 nếu giám thị $g$ coi phòng $r$ ở ca $t$ |
| $a_{i,d}$ | Số nguyên $\ge 0$ | Biến phụ cho A-S1 |
| $b_{i,d}$ | Số nguyên $\ge 0$ | Biến phụ cho A-S2 |
| $\Lambda^{\max}, \Lambda^{\min}$ | Số nguyên $\ge 0$ | Biến phụ cho A-S5 |

Biến $u$ chỉ được tạo với $r \in R_c$. Vì vậy ràng buộc A-H5 (đúng loại phòng) được đảm bảo ngay từ cách khai báo biến.

Với môn chỉ có một lượt ($c \in C^{U}$), mọi sinh viên của môn đều thi lượt đó, nên không cần biến $q$. Để viết gọn, dùng các biểu thức sau:

- Sinh viên $i$ có thi môn $c$ ở lượt bắt đầu ca $s$ hay không:

$$
\pi_{i,c,s} =
\begin{cases}
x_{c,s} & \text{nếu } c \in C^{U} \\
q_{i,c,s} & \text{nếu } c \in C^{P}
\end{cases}
$$

- Số sinh viên của lượt $(c,s)$:

$$
N_{c,s} =
\begin{cases}
n_c \, x_{c,s} & \text{nếu } c \in C^{U} \\
\sum_{i \in I_c} q_{i,c,s} & \text{nếu } c \in C^{P}
\end{cases}
$$

- Phòng $r$ có đang được dùng ở ca $t$ hay không:

$$
o_{r,t} = \sum_{c \in C : r \in R_c} \ \sum_{s \in S_c(t)} u_{c,r,s}
$$

- Số lượt sinh viên $i$ bắt đầu trong ngày $d$ (lượt 2 ca chỉ tính một lần vì chỉ đếm ca bắt đầu):

$$
E_{i,d} = \sum_{c \in C_i} \ \sum_{s \in S_c \cap T_d} \pi_{i,c,s}
$$

- Số ca coi thi của giám thị $g$:

$$
\lambda_g = \sum_{r \in R} \sum_{t \in T} w_{g,r,t}
$$

Tất cả các biểu thức trên đều tuyến tính theo biến.

### A.5. Ràng buộc cứng

#### A-H1. Số lượt của mỗi môn

Mỗi môn có ít nhất 1 lượt và không quá $L_c$ lượt. Với môn chỉ có một lượt, ràng buộc này trở thành "đúng 1 lượt".

$$
1 \le \sum_{s \in S_c} x_{c,s} \le L_c \qquad \forall c \in C
$$

Việc mỗi lượt chiếm 1 hay 2 ca, và lượt 2 ca chỉ bắt đầu ở ca 1 hoặc ca 3, đã nằm sẵn trong định nghĩa $S_c$ và $\mathrm{Cov}(c,s)$.

#### A-H9. Mỗi sinh viên thi đúng một lượt của môn được chia lượt

Với $c \in C^{P}$:

$$
\sum_{s \in S_c} q_{i,c,s} = 1 \qquad \forall c \in C^{P},\ i \in I_c
$$

$$
q_{i,c,s} \le x_{c,s} \qquad \forall c \in C^{P},\ i \in I_c,\ s \in S_c
$$

$$
x_{c,s} \le \sum_{i \in I_c} q_{i,c,s} \qquad \forall c \in C^{P},\ s \in S_c
$$

Ràng buộc thứ nhất: mỗi sinh viên được xếp đúng một lượt. Ràng buộc thứ hai: chỉ được xếp vào lượt có mở. Ràng buộc thứ ba: không mở lượt nào mà không có sinh viên (tránh lượt rỗng vẫn chiếm phòng và giám thị).

Với $c \in C^{U}$, A-H9 tự động đúng vì $\pi_{i,c,s} = x_{c,s}$ và môn có đúng một lượt.

#### A-H2. Không sinh viên nào thi hai lượt trùng ca

$$
\sum_{c \in C_i} \ \sum_{s \in S_c(t)} \pi_{i,c,s} \le 1 \qquad \forall i \in I,\ t \in T
$$

Tổng bên trái đếm số lượt sinh viên $i$ đang ngồi thi ở ca $t$, kể cả lượt 2 ca đã bắt đầu từ ca trước. Nhờ dùng $q_{i,c,s}$ (sinh viên gắn trực tiếp với ca bắt đầu) nên ràng buộc vẫn tuyến tính với môn chia lượt.

#### A-H3. Đủ chỗ cho mỗi lượt

$$
N_{c,s} \le \sum_{r \in R_c} \kappa_r \, u_{c,r,s} \qquad \forall c \in C,\ s \in S_c
$$

$$
u_{c,r,s} \le x_{c,s} \qquad \forall c \in C,\ r \in R_c,\ s \in S_c
$$

Ràng buộc thứ hai đảm bảo chỉ lượt có mở mới được giữ phòng. Ràng buộc này viết riêng cho từng phòng thay vì gộp thành $\sum_r u_{c,r,s} \le \lvert R_c \rvert \, x_{c,s}$, theo quy tắc 9 và 10 của Daskin (xem A.9).

Mô hình chỉ quyết định tổng số chỗ của mỗi lượt, không quyết định sinh viên nào ngồi phòng nào. Việc chia sinh viên vào từng phòng làm ở bước hậu xử lý (A.10) và luôn làm được, vì tổng sức chứa đã đủ.

#### A-H4. Mỗi phòng, mỗi ca tối đa một môn

$$
o_{r,t} \le 1 \qquad \forall r \in R,\ t \in T
$$

Vì $o_{r,t}$ tính cả các lượt 2 ca đang diễn ra, phòng của lượt 2 ca bị giữ suốt hai ca.

#### A-H5. Đúng loại phòng

Đảm bảo bằng miền của biến $u$: $u_{c,r,s}$ chỉ tồn tại khi $r \in R_c$. Do đó môn thi máy chỉ vào phòng máy, và phòng máy không bao giờ được gán cho môn thi viết.

#### A-H6. Không dùng phòng vào ca bận

$$
o_{r,t} = 0 \qquad \forall r \in R,\ t \in B^{R}_r
$$

Khi cài đặt, có thể không tạo biến $u_{c,r,s}$ nào có $\mathrm{Cov}(c,s) \cap B^{R}_r \neq \emptyset$. Hai cách cho cùng kết quả; cách sau làm mô hình nhỏ hơn.

#### A-H7. Đủ giám thị, và lượt 2 ca giữ nguyên giám thị

Mỗi phòng đang dùng có đúng $\nu = 2$ giám thị; phòng không dùng thì không có giám thị:

$$
\sum_{g \in G} w_{g,r,t} = \nu \, o_{r,t} \qquad \forall r \in R,\ t \in T
$$

Lượt 2 ca giữ nguyên giám thị ở cả hai ca. Gọi $m_{r,s} = \sum_{c \in C : \ell_c = 2,\ r \in R_c,\ s \in S_c} u_{c,r,s}$ là chỉ báo "có lượt 2 ca bắt đầu ở phòng $r$, ca $s$" (nhận giá trị 0 hoặc 1 nhờ A-H4). Khi đó:

$$
w_{g,r,s} - w_{g,r,s^{+}} \le 1 - m_{r,s} \qquad \forall g \in G,\ r \in R,\ s \in T \text{ với } k(s) \in \{1,3\},\ s^{+} \in T
$$

$$
w_{g,r,s^{+}} - w_{g,r,s} \le 1 - m_{r,s} \qquad \text{(cùng miền chỉ số)}
$$

Khi $m_{r,s} = 1$, hai bất đẳng thức buộc $w_{g,r,s} = w_{g,r,s^{+}}$ với mọi giám thị. Khi $m_{r,s} = 0$, chúng không ràng buộc gì (vế phải bằng 1). Vế phải chỉ dùng hằng số 1 chứ không phải một số M lớn, nên đây không phải ràng buộc big-M lỏng.

#### A-H8. Giám thị không coi hai nơi cùng lúc, không coi vào ca bận

$$
\sum_{r \in R} w_{g,r,t} \le 1 \qquad \forall g \in G,\ t \in T
$$

$$
w_{g,r,t} = 0 \qquad \forall g \in G,\ r \in R,\ t \in B^{G}_g
$$

Với lượt 2 ca, giám thị được giữ ở cả hai ca (A-H7), nên nếu giám thị bận một trong hai ca thì cũng không thể coi lượt đó.

#### A-H10. (Tùy chọn) Giám thị không coi môn mình dạy

Chỉ thêm khi $\theta = 1$:

$$
w_{g,r,t} + \sum_{c \in \Phi_g : r \in R_c} \ \sum_{s \in S_c(t)} u_{c,r,s} \le 1 \qquad \forall g \in G,\ r \in R,\ t \in T
$$

Nếu phòng $r$ ở ca $t$ đang thi một môn giảng viên $g$ dạy thì $w_{g,r,t} = 0$. Tổng thứ hai không vượt quá 1 nhờ A-H4.

#### Ràng buộc bổ trợ (không làm thay đổi tập nghiệm)

Số phòng đang dùng ở mỗi ca không vượt quá số giám thị rảnh chia cho 2:

$$
\sum_{r \in R} o_{r,t} \le \left\lfloor \frac{\lvert \{ g \in G : t \notin B^{G}_g \} \rvert}{\nu} \right\rfloor \qquad \forall t \in T
$$

Ràng buộc này suy ra được từ A-H7 và A-H8 nên không loại bỏ lời giải hợp lệ nào. Nó được thêm vào để solver phát hiện sớm trường hợp thiếu giám thị, và cần thiết cho chiến lược giải hai pha (A.7).

### A.6. Ràng buộc mềm và hàm mục tiêu

Mỗi ràng buộc mềm được đo bằng một đại lượng phạt $P_k \ge 0$.

#### A-S1. Thi từ 2 môn trở lên trong một ngày

$$
a_{i,d} \ge E_{i,d} - 1, \quad a_{i,d} \ge 0 \qquad \forall i \in I,\ d \in D
$$

$$
P_1 = \sum_{i \in I} \sum_{d \in D} a_{i,d}
$$

$a_{i,d}$ là số môn "thừa" trong ngày: thi 1 môn thì 0, thi 2 môn thì 1, thi 3 môn thì 2. Vì hàm mục tiêu cực tiểu hóa nên solver luôn đẩy $a_{i,d}$ xuống đúng bằng $\max(0, E_{i,d} - 1)$.

Lưu ý: $P_1$ đếm số môn thừa, còn KPI "số sinh viên thi từ 2 môn/ngày" trong scope đếm số sinh viên. Hai đại lượng khác nhau nhưng cùng chiều; KPI được tính lại từ lời giải ở bước hậu xử lý.

#### A-S2. Giãn cách giữa các môn

Trong mỗi cửa sổ hai ngày thi liên tiếp, sinh viên nên có tối đa một môn:

$$
b_{i,d} \ge E_{i,d} + E_{i,d'} - 1, \quad b_{i,d} \ge 0 \qquad \forall i \in I,\ (d,d') \in Q
$$

$$
P_2 = \sum_{i \in I} \sum_{(d,d') \in Q} b_{i,d}
$$

Hai môn cùng một ngày bị phạt ở cả A-S1 và A-S2. Điều này là cố ý: thi cùng ngày tệ hơn thi hai ngày liền nhau, nên phải chịu phạt nặng hơn.

#### A-S3. Chia một lượt ra quá nhiều phòng

Phạt mỗi phòng vượt quá phòng đầu tiên của một lượt:

$$
P_3 = \sum_{c \in C} \sum_{s \in S_c} \Big( \sum_{r \in R_c} u_{c,r,s} - x_{c,s} \Big)
$$

Mỗi số hạng không âm vì A-H3 buộc lượt có mở phải có ít nhất một phòng (trừ khi $N_{c,s} = 0$, điều mà A-H9 và $n_c \ge 1$ đã loại trừ).

#### A-S4. Lãng phí chỗ

Số chỗ trống nhân với số ca bị chiếm:

$$
P_4 = \sum_{c \in C} \sum_{s \in S_c} \ell_c \Big( \sum_{r \in R_c} \kappa_r \, u_{c,r,s} - N_{c,s} \Big)
$$

Mỗi số hạng không âm nhờ A-H3. Nhân với $\ell_c$ vì lượt 2 ca giữ chỗ trống suốt hai ca.

#### A-S5. Công bằng giữa các giám thị

$$
\Lambda^{\max} \ge \lambda_g, \quad \Lambda^{\min} \le \lambda_g \qquad \forall g \in G
$$

$$
P_5 = \Lambda^{\max} - \Lambda^{\min}
$$

$P_5$ là chênh lệch giữa người coi nhiều ca nhất và người coi ít ca nhất. Chỉ tính trên tập $G$ (người tham gia coi thi). Giảng viên bận gần hết đợt thi nên được loại khỏi $G$ ngay từ dữ liệu, nếu không $\Lambda^{\min}$ sẽ bị kéo xuống và mục tiêu này mất ý nghĩa.

#### A-S6. Số lượt thi

Phạt mỗi lượt vượt quá lượt đầu tiên của một môn:

$$
P_6 = \sum_{c \in C} \Big( \sum_{s \in S_c} x_{c,s} - 1 \Big)
$$

Môn thi máy quá đông bắt buộc phải có ít nhất $\lceil n_c / \sum_{r \in R_c} \kappa_r \rceil$ lượt. Phần bắt buộc này cũng bị tính vào $P_6$, nhưng là hằng số với mọi lời giải hợp lệ nên không ảnh hưởng đến việc chọn lời giải.

#### Hàm mục tiêu

$$
\min \ Z = \omega_1 P_1 + \omega_2 P_2 + \omega_3 P_3 + \omega_4 P_4 + \omega_5 P_5 + \omega_6 P_6
$$

Trọng số mặc định. CP-SAT chỉ nhận hệ số nguyên nên mọi trọng số là số nguyên:

| Trọng số | Giá trị | Đơn vị của $P_k$ | Lý do |
|---|---|---|---|
| $\omega_1$ (A-S1) | 100 | Môn thừa trong ngày | Ưu tiên cao nhất về trải nghiệm sinh viên |
| $\omega_2$ (A-S2) | 30 | Môn thừa trong cửa sổ 2 ngày | Quan trọng nhưng kém A-S1 |
| $\omega_3$ (A-S3) | 50 | Phòng thêm | Mỗi phòng thêm tốn 2 giám thị |
| $\omega_4$ (A-S4) | 1 | Chỗ trống × ca | Đơn vị nhỏ nhất, dùng làm mốc |
| $\omega_5$ (A-S5) | 20 | Ca coi thi chênh lệch | |
| $\omega_6$ (A-S6) | 200 | Lượt thêm (đề thêm) | Ra thêm một đề tốn công nhất |

Cách đọc: thêm một lượt (tốn 200) chỉ đáng khi nó giúp ít nhất 2 sinh viên không phải thi 2 môn cùng ngày (tiết kiệm 2 × 100). Một phòng thêm (tốn 50) đáng giá bằng 50 chỗ trống × ca.

Các trọng số này là điểm khởi đầu. Phần thực nghiệm sẽ thay đổi chúng để xem lời giải thay đổi ra sao (phân tích độ nhạy, câu hỏi thứ 5 của Daskin), và có thể vẽ đường cong đánh đổi giữa hai mục tiêu, ví dụ $P_1$ và $P_6$.

### A.7. Chiến lược giải

Mặc định giải toàn bộ mô hình một lần bằng CP-SAT, với giới hạn thời gian (mặc định 300 giây). Kết quả trả về một trong bốn trạng thái:

| Trạng thái CP-SAT | Ý nghĩa với người dùng |
|---|---|
| `OPTIMAL` | Lịch tối ưu theo hàm mục tiêu |
| `FEASIBLE` | Lịch hợp lệ, chưa chứng minh tối ưu (hết thời gian) |
| `INFEASIBLE` | Không tồn tại lịch thỏa mọi ràng buộc cứng; báo nguyên nhân theo A.8 |
| `UNKNOWN` | Hết thời gian mà chưa tìm được lịch hợp lệ nào |

Nếu mô hình đầy đủ chạy quá chậm với bộ `large`, dùng chiến lược hai pha:

1. Pha 1: bỏ biến $w$ và các ràng buộc A-H7, A-H8, A-H10, mục tiêu A-S5. Giữ ràng buộc bổ trợ ở cuối A.5 để đảm bảo mỗi ca không dùng nhiều phòng hơn số giám thị cho phép. Giải tìm lượt, ca, phòng và phân sinh viên.
2. Pha 2: cố định kết quả pha 1, chỉ giải phần giám thị (biến $w$, A-H7, A-H8, A-H10, A-S5). Bài toán này nhỏ và giải rất nhanh.

Hai pha có thể cho lời giải kém hơn giải một lần, vì pha 1 không biết lịch bận của từng giám thị. Nếu pha 2 vô nghiệm (hiếm, chỉ xảy ra khi bật A-H10 hoặc khi ràng buộc giữ nguyên giám thị cho lượt 2 ca không thỏa được), quay lại giải một lần với giới hạn thời gian dài hơn. Khi viết báo cáo, so sánh hai cách này là một phần thực nghiệm tốt.

Kết quả thử ở A.13 cho thấy phần giám thị làm thời gian chứng minh tối ưu tăng rõ rệt, kể cả với dữ liệu rất nhỏ. Lý do là các giám thị rảnh cùng lúc có thể đổi chỗ cho nhau mà không làm thay đổi giá trị mục tiêu, nên solver phải xét rất nhiều lời giải tương đương. Vì vậy khi cài đặt cần làm cả hai cách, và dự kiến dùng hai pha làm mặc định cho bộ `medium` và `large`. Số đo thực nghiệm ở A.13 xác nhận lựa chọn này.

### A.8. Kiểm tra dữ liệu trước khi giải

Các kiểm tra sau chạy trước khi dựng mô hình. Mỗi lỗi được báo bằng một thông điệp chỉ rõ đối tượng gây lỗi.

| Mã | Điều kiện lỗi | Mức độ |
|---|---|---|
| P1 | Có môn $\tau_c > 280$ | Lỗi, dừng |
| P2 | Có môn $n_c = 0$ | Cảnh báo, bỏ môn đó khỏi mô hình |
| P3 | Có môn $R_c = \emptyset$ (ví dụ thi máy nhưng khoa không có phòng máy) | Lỗi, dừng |
| P4 | Có môn $S_c = \emptyset$ | Lỗi, dừng |
| P5 | Có môn $n_c > L_c \cdot \sum_{r \in R_c} \kappa_r$ (kể cả dùng hết phòng ở mọi lượt vẫn không đủ chỗ) | Lỗi, dừng |
| P6 | $\lvert G \rvert < \nu$ | Lỗi, dừng |
| P7 | Môn thi viết có $L_c \ge 2$ | Thông tin: môn này được phép chia lượt theo dữ liệu |
| P8 | Có cặp (sinh viên, môn) bị lặp trong dữ liệu đăng ký | Cảnh báo, loại bản ghi trùng |
| P9 | Có phòng $\kappa_r \le 0$ | Cảnh báo, loại phòng đó khỏi mô hình |

Các kiểm tra này là điều kiện cần, không phải điều kiện đủ. Dữ liệu qua hết các kiểm tra vẫn có thể vô nghiệm, ví dụ khi có quá nhiều môn trùng sinh viên so với số ca. Khi đó CP-SAT trả về `INFEASIBLE`. Để gợi ý nguyên nhân, chạy lại lần lượt với một nhóm ràng buộc được nới ra và báo nhóm nào làm mô hình có nghiệm trở lại.

#### Chẩn đoán khi vô nghiệm

Cài đặt ở `src/diagnose.py`, tự chạy trong `src/run.py` và `src/reschedule.py` mỗi khi solver trả về `INFEASIBLE` (tắt bằng `--no-diagnose`). Có ba nhóm ràng buộc được thử bỏ, mỗi lần bỏ một nhóm:

| Nhóm | Ràng buộc bị bỏ | Nếu bỏ nhóm này mà có lịch, nghĩa là |
|---|---|---|
| Giám thị | Biến $w$, A-H7, A-H8, A-H10 và ràng buộc bổ trợ | Không đủ giám thị rảnh để coi thi |
| A-H2 | Không trùng lịch sinh viên | Quá ít ca so với số môn một số sinh viên phải thi |
| A-H6 | Lịch bận của phòng | Phòng bận quá nhiều ca |

Mỗi lần thử chỉ tìm một lịch hợp lệ bất kỳ, không có hàm mục tiêu, với giới hạn 30 giây (hoặc `time_limit_sec` nếu nhỏ hơn). Kết quả được báo bằng mã N01–N05 (data_schema mục 5):

1. Mỗi nhóm bỏ đi mà có lịch được báo một thông báo N01, kèm gợi ý sửa dữ liệu. Có thể có nhiều hơn một nhóm.
2. Nếu không nhóm nào riêng lẻ đủ, thử bỏ cả ba nhóm cùng lúc. Có lịch thì báo N02 (nhiều nguyên nhân cùng lúc). Vẫn vô nghiệm thì báo N03: nguyên nhân nằm ở phần còn lại (A-H1, A-H3, A-H4, A-H5), tức không đủ phòng phù hợp hoặc không đủ ca để mở đủ số lượt cần thiết.
3. Lần thử nào hết giờ mà chưa kết luận được thì báo N04. N05 ghi tổng thời gian chẩn đoán.

Chẩn đoán luôn dùng CP-SAT, kể cả khi lần giải chính dùng PuLP + CBC. Kết quả kiểm thử trên các biến thể của bộ `toy` (`tests/test_reschedule.py`), mỗi trường hợp chẩn đoán xong dưới 1 giây:

| Biến thể | Chẩn đoán |
|---|---|
| Chỉ 2 giảng viên coi thi | N01, nhóm giám thị |
| Chỉ 7 ca (ngày 14/12 và ca 1–3 ngày 15/12) | N01, nhóm A-H2 |
| Phòng máy duy nhất bận từ 15/12 đến 17/12 | N01, nhóm A-H6 |
| Chỉ 2 ca (ca 1, ca 2 ngày 14/12) | N03: một phòng máy với 2 ca không đủ cho các lượt thi máy |

### A.9. Đối chiếu với 10 quy tắc lập mô hình của Daskin

| Quy tắc | Áp dụng trong mô hình |
|---|---|
| 1. Định nghĩa rõ mọi tập hợp bằng lời | Bảng A.2 |
| 2. Tách bạch tập hợp, đầu vào, biến quyết định | Ba bảng riêng A.2, A.3, A.4 |
| 3. Có chỉ số trong ký hiệu thì có trong lời định nghĩa | Mọi ký hiệu có chỉ số đều nêu chỉ số trong cột ý nghĩa |
| 4. Không để chỉ số lơ lửng trong hàm mục tiêu | Mọi chỉ số trong $P_1, \dots, P_6$ đều nằm dưới một dấu tổng |
| 5. Mục tiêu và mỗi ràng buộc chứa biến quyết định | Đã kiểm tra từng công thức |
| 6. Mọi nhóm biến phải liên kết với nhau | $u \le x$; $q \le x$ và $x \le \sum q$; $w$ nối với $u$ qua $o_{r,t}$ (A-H7) |
| 7. Mỗi chỉ số hoặc lấy tổng hoặc "với mọi", không cả hai | Đã kiểm tra từng công thức |
| 8. Giữ mô hình tuyến tính | Mọi ràng buộc tuyến tính; không có tích hai biến nhờ biến $q_{i,c,s}$ gắn trực tiếp với ca bắt đầu |
| 9. Tránh big-M | Không dùng; ràng buộc giữ nguyên giám thị ở A-H7 chỉ dùng hằng số 1 |
| 10. Tách nhỏ ràng buộc | $u_{c,r,s} \le x_{c,s}$ và $q_{i,c,s} \le x_{c,s}$ viết cho từng phần tử thay vì gộp |

### A.10. Hậu xử lý

Sau khi có lời giải:

1. Chia sinh viên của mỗi lượt vào từng phòng của lượt đó, theo thứ tự mã sinh viên, lấp đầy phòng lớn trước. Luôn làm được vì tổng sức chứa đã đủ (A-H3).
2. Ghép mỗi phòng với hai giám thị đã được xếp.
3. Tính KPI theo định nghĩa trong scope (mục 7).
4. Chạy validator: một chương trình độc lập với solver, kiểm tra lại từng ràng buộc cứng trên lời giải cuối cùng và báo vi phạm theo mã.

### A.11. Kích thước mô hình ước lượng

Ước lượng giới hạn trên, với 48 ca, giả sử mỗi sinh viên học 4–5 môn, 1/3 số môn thi trên máy và được chia lượt:

| Bộ dữ liệu | Môn | Phòng | Sinh viên | Giám thị | Biến nhị phân (xấp xỉ) | Ràng buộc A-H2 |
|---|---|---|---|---|---|---|
| `toy` | 5 | 3 | 50 | 6 | 3 nghìn | 2,4 nghìn |
| `medium` | 30 | 10 | 500 | 25 | 55 nghìn | 24 nghìn |
| `large` | 60 | 15 | 1.000 | 40 | 140 nghìn | 48 nghìn |

Phần lớn biến đến từ $q$ (phân sinh viên vào lượt) và $w$ (giám thị). Các cách thu nhỏ mô hình khi cài đặt, không làm thay đổi tập nghiệm:

- Không tạo biến cho ca phòng bận và ca giám thị bận (A-H6, A-H8).
- Với sinh viên chỉ học các môn không chia lượt, nhiều sinh viên có cùng tập môn sẽ sinh ra những ràng buộc A-H2 giống hệt nhau; chỉ cần giữ một bản.
- Dùng chiến lược hai pha ở A.7.

### A.12. Những điều mô hình cố ý không xét

Để tránh hiểu lầm khi đọc kết quả:

- Không xếp chỗ ngồi cụ thể trong phòng; chỉ chia sinh viên vào phòng ở bước hậu xử lý.
- Không giới hạn số ca coi thi tối đa của một giám thị trong một ngày; chỉ cân bằng tổng số ca (A-S5).
- Không xét quãng đường di chuyển giữa các tòa nhà.
- Giả định mỗi lượt của môn chia lượt có đề riêng; việc ra đề nằm ngoài hệ thống.
- Không xét nguyện vọng ngày thi của sinh viên.

### A.13. Kiểm chứng đặc tả

Đặc tả này đã được kiểm chứng bằng một bản cài đặt thử với OR-Tools CP-SAT 9.15, viết đúng theo các công thức A.4 đến A.6, cùng một bộ kiểm tra viết độc lập. Bộ kiểm tra không dùng lại công thức của mô hình mà soát lời giải trực tiếp theo luật trong `scope.md`, tính bằng giờ đồng hồ thật của từng ca.

Dữ liệu thử: 4 ngày, 15 ca (một ca nghỉ giữa buổi sáng), 3 phòng (2 thường, 1 máy), 30 sinh viên, 6 giám thị, 5 môn gồm: môn thi viết cần 2 phòng, môn thi viết 180 phút (2 ca), môn thi máy 20 sinh viên trên phòng 8 máy (buộc chia ít nhất 3 lượt), môn thi máy 150 phút buộc chia lượt, môn thi viết được phép chia lượt. Có phòng bận và giám thị bận.

| Kịch bản | Kết quả mong đợi | Kết quả |
|---|---|---|
| Dữ liệu chuẩn, A-H10 tắt và bật | Có lời giải, không vi phạm | Tối ưu, không vi phạm; điểm phạt tính lại độc lập khớp với solver |
| Môn thi máy 20 sinh viên nhưng chỉ cho 1 lượt | Vô nghiệm | `INFEASIBLE` |
| Chỉ còn 1 giám thị | Vô nghiệm | `INFEASIBLE` |
| 8 bộ dữ liệu ngẫu nhiên × 2 trạng thái A-H10 | Không vi phạm | 16/16 không vi phạm |
| Cố ý làm hỏng lời giải theo 8 cách (bỏ lượt, sai ca 2 ca, sai loại phòng, thiếu chỗ, trùng lượt, trùng ca, thiếu giám thị, giám thị coi môn mình dạy) | Bộ kiểm tra phải phát hiện | 8/8 phát hiện đúng mã lỗi |

Thời gian chứng minh tối ưu trên dữ liệu thử: 20 đến 56 giây tùy biến thể; bỏ mục tiêu A-S5 nhanh hơn. Đây là cơ sở cho khuyến nghị dùng hai pha ở A.7.

#### Solver đối chứng PuLP + CBC

Mô hình được cài đặt lần thứ hai bằng PuLP 3.3.2 với bộ giải CBC 2.10.3 (`src/exam_solver_pulp.py`), độc lập với CP-SAT. Kết quả với `configs/default.json`, CBC chạy một luồng:

| Bộ dữ liệu | Giới hạn | Kết quả CBC | Ghi chú |
|---|---|---|---|
| `toy` | 60 giây | `FEASIBLE`, mục tiêu 2391, không vi phạm | Tìm ra lời giải đạt giá trị tối ưu ở khoảng giây thứ 9, trùng với CP-SAT |
| `toy` | 300 giây | `FEASIBLE`, mục tiêu 2391 | Cận dưới chỉ đạt 2285, còn cách tối ưu khoảng 4%; không chứng minh được tối ưu |
| `toy`, bỏ A-S5 | 300 giây | `FEASIBLE`, mục tiêu 2391 | Cận dưới 2229; khác CP-SAT, phần giám thị không phải nguyên nhân chính |
| Dữ liệu chỉ có 2 ca (vô nghiệm) | 60 giây | `INFEASIBLE` sau 0,2 giây | |
| `medium` (64 nghìn biến, 88 nghìn ràng buộc) | 300 giây | `UNKNOWN` | Chưa xong tiền xử lý và nút gốc; bị dừng ở hạn cứng 360 giây (thông báo S01) |

Nhận xét: CP-SAT chứng minh tối ưu bộ `toy` trong 20–56 giây và tìm được lời giải hợp lệ cho `medium` trong 300 giây, còn CBC không chứng minh được tối ưu `toy` và không tìm được lời giải nào cho `medium`. Nguyên nhân là nới lỏng tuyến tính của mô hình xếp lịch cho cận dưới yếu (nhiều biến nhị phân gắn với nhau qua các ràng buộc phủ ca), nên phương pháp nhánh và cận phải duyệt rất nhiều nút; CP-SAT kết hợp lan truyền ràng buộc và học mệnh đề nên xử lý loại bài toán này tốt hơn.

Ba vấn đề kỹ thuật của CBC phát hiện khi cài đặt, đã xử lý trong code:

1. Bản CBC đóng gói trong PuLP cho Windows bị treo ngay khi bắt đầu nhánh và cận nếu truyền tham số `-threads`, kể cả `threads=1`. Vì vậy không truyền tham số này; CBC chạy một luồng.
2. Khi CBC dừng do hết giờ mà đã có lời giải, `prob.status` của PuLP vẫn là "Optimal". Trạng thái được đọc từ `prob.sol_status`, nơi phân biệt được tối ưu (1) và chỉ khả thi (2).
3. Với mô hình lớn, CBC không dừng đúng giới hạn thời gian vì chỉ kiểm tra giới hạn giữa các bước. Solver đặt thêm hạn cứng (giới hạn cộng 30 giây hoặc 20%, lấy số lớn hơn) và dừng CBC khi vượt quá.

#### Kết quả thực nghiệm hiệu năng

Thực nghiệm có hệ thống (KHOE-4, chi tiết ở `experiments/README.md`): 30 lần giải gồm CP-SAT `single` và `two_phase` trên `toy`, `toy_gen`, `medium`, `large`, cộng PuLP + CBC trên hai bộ nhỏ. Mỗi tổ hợp chạy 3 lần (CP-SAT với `random_seed` 0, 1, 2), giới hạn 300 giây, CP-SAT 8 luồng. Thêm 6 kịch bản xếp lại trên `medium` và `large`.

Khoảng cách tới cận dưới:

$$
\text{gap} = \frac{Z - \max(B, 0)}{Z}
$$

với $Z$ là giá trị mục tiêu của lời giải và $B$ là cận dưới solver báo. Vì $Z \ge 0$ nên cận âm không cho thông tin gì hơn cận 0 và được thay bằng 0. Gap bằng 0 là đã chứng minh tối ưu; gap bằng 1 là chưa chứng minh được gì.

<!-- RESULTS_BEGIN -->
Kết quả dưới đây tổng hợp từ `experiments/results/perf.csv` và `experiments/results/reschedule.csv`. Chi tiết phương pháp và phân tích: [Báo cáo thực nghiệm](../experiments/README.md).

| Dữ liệu | Chiến lược | Nghiệm hợp lệ / 3 | Z TB | Thời gian TB (s) | Gap TB |
|---|---|---:|---:|---:|---:|
| `medium` | `single` | 3/3 | 14994.7 | 300.7 | 1.000 |
| `medium` | `two_phase` | 3/3 | 13050.3 | 240.8 | 1.000 |
| `large` | `single` | 3/3 | 43494.0 | 302.1 | 1.000 |
| `large` | `two_phase` | 3/3 | 38758.0 | 242.6 | 1.000 |

Dấu «—» là thiếu giá trị, không phải 0. Cận dưới âm được kẹp về 0 vì Z không âm, nên gap = 1 nghĩa là chưa chứng minh được gì.

- Medium: đề xuất `two_phase` (single 3/3 nghiệm hợp lệ, two_phase 3/3; Z TB 14994.7 / 13050.3; gap TB 1.000 / 1.000; thời gian TB 300.7s / 240.8s).
- Large: đề xuất `two_phase` (single 3/3 nghiệm hợp lệ, two_phase 3/3; Z TB 43494.0 / 38758.0; gap TB 1.000 / 1.000; thời gian TB 302.1s / 242.6s).
- Xếp lại trên large: đạt KPI dưới 60 giây trên cả ba kịch bản đã đo; giữ được chất lượng lịch ở cả ba kịch bản.
<!-- RESULTS_END -->

Kết luận:

- `two_phase` tốt hơn `single` trên `medium` và `large`: cùng seed thì `two_phase` luôn cho Z thấp hơn (trung bình thấp hơn 13% trên `medium`, 11% trên `large`), dù chỉ dùng khoảng 240 trong 300 giây. Pha 1 không có biến giám thị nên nhỏ hơn và không bị các lời giải tương đương do đổi chỗ giám thị làm chậm (A.7). Đây là chiến lược khuyến nghị cho `medium` và `large`. Mặc định trong `configs/default.json` vẫn là `single`, vì với dữ liệu nhỏ `single` chứng minh được tối ưu.
- Trên `medium` và `large`, cận dưới của cả hai chiến lược đều âm, nên gap bằng 1: không chứng minh được gì về chất lượng lời giải, và gap không dùng để so sánh hai chiến lược.
- CP-SAT chứng minh tối ưu `toy` trong 4–14 giây và `toy_gen` trong 18–26 giây. CBC tìm được lời giải tốt cho hai bộ này nhưng chạy hết 300 giây mà không chứng minh được tối ưu, và một lần trên `toy_gen` dừng ở 3710 thay vì 3650. Nguyên nhân như đã nêu ở mục trên.
- Xếp lại: lần đo đầu với cách cũ (A.14, chỉ gợi ý bằng lịch cũ) cho cả 6 kịch bản dưới 60 giây, nhưng ba sự cố cùng lúc trên `large` làm gần như cả lịch bị xếp lại (Z từ 37660 lên 108280, 999 trong 1000 sinh viên bị ảnh hưởng). Sau khi thêm bước xếp lại cục bộ (A.14), đo lại cả 6 kịch bản: 42–47 giây, Z tăng không quá 0,5%, 1–3 lượt thay đổi, không lượt nào dời ca. Trên cùng lịch nền và cùng ba sự cố, cách cũ đổi 77 lượt và ảnh hưởng 985 sinh viên, cách mới đổi 2 lượt và ảnh hưởng 83 sinh viên.

### A.14. Xếp lại khi có sự cố

Bối cảnh: lịch thi đã công bố thì xảy ra sự cố, ví dụ một phòng hỏng máy hoặc một giảng viên bận đột xuất. Dịch vụ tốt cần lịch mới vẫn hợp lệ, xáo trộn càng ít càng tốt so với lịch cũ, và có trong vòng 1 phút (scope mục 7). Giải lại từ đầu không đạt yêu cầu này, vì solver không biết lịch cũ nên có thể ra một lịch khác hẳn.

#### Đầu vào

- Bộ dữ liệu gốc và lịch cũ (file `schedule.json` của chính bộ dữ liệu đó).
- Danh sách sự cố. Mỗi sự cố có đúng dạng một dòng của `unavailability.csv`: loại (`room` hoặc `lecturer`), mã, ngày, và ca hoặc cả ngày. Sự cố được thêm vào $B^{R}_r$ hoặc $B^{G}_g$.

Mô hình giữ nguyên mọi ràng buộc cứng ở A.5 và điểm phạt ở A.6. Chỉ thêm điểm phạt thay đổi và lời giải gợi ý.

#### Điểm phạt thay đổi

Gọi $\bar{X}$, $\bar{U}$, $\bar{Q}$, $\bar{W}$ là các bộ chỉ số mà $x$, $u$, $q$, $w$ bằng 1 trong lịch cũ ($\bar{Q}$ chỉ gồm các môn chia lượt). Biến nào không còn tồn tại (ví dụ $u$ của phòng vừa báo hỏng) được coi là bằng 0, tức thay đổi đó chắc chắn xảy ra.

| Mã | Đếm | Công thức |
|---|---|---|
| A-R1 | Lượt cũ không còn mở ở ca bắt đầu cũ (dời ca) | $R_1 = \sum_{(c,s) \in \bar{X}} (1 - x_{c,s})$ |
| A-R2 | Lượt cũ giữ ca nhưng bỏ một phòng cũ (đổi phòng) | $R_2 = \sum_{(c,r,s) \in \bar{U}} (x_{c,s} - u_{c,r,s})$ |
| A-R3 | Sinh viên của môn chia lượt bị chuyển khỏi lượt cũ | $R_3 = \sum_{(i,c,s) \in \bar{Q}} (1 - q_{i,c,s})$ |
| A-R4 | Giám thị bị bỏ khỏi một ca coi thi cũ (phòng, ca) | $R_4 = \sum_{(g,r,t) \in \bar{W}} (1 - w_{g,r,t})$ |

Vì $u_{c,r,s} \le x_{c,s}$, mỗi số hạng của $R_2$ bằng 0 hoặc 1, và bằng 1 đúng khi lượt giữ ca mà bỏ phòng $r$. Lượt bị dời ca đã được tính ở A-R1 nên không bị tính thêm ở A-R2. Mọi công thức đều tuyến tính, không cần biến phụ.

Hàm mục tiêu khi xếp lại:

$$
\min \ Z + \rho_1 R_1 + \rho_2 R_2 + \rho_3 R_3 + \rho_4 R_4
$$

Trọng số mặc định (khóa `reschedule.weights` trong cấu hình, data_schema mục 6):

| Trọng số | Giá trị | Lý do |
|---|---|---|
| $\rho_1$ (A-R1) | 1000 | Dời ca buộc toàn bộ sinh viên và giám thị của lượt xem lại lịch; đắt bằng 5 lượt thêm (A-S6) |
| $\rho_2$ (A-R2) | 100 | Đổi phòng giữ nguyên giờ thi, chỉ cần báo sinh viên của phòng đó |
| $\rho_3$ (A-R3) | 50 | Chuyển một sinh viên sang lượt khác chỉ đáng khi giảm được ít nhất 2 đơn vị A-S2 hoặc nửa đơn vị A-S1 |
| $\rho_4$ (A-R4) | 20 | Đổi giám thị một ca coi thi, ngang một đơn vị chênh lệch tải A-S5 |

Khi thử trên `toy`, với $\rho_3$ bằng 10, 30, 50 hoặc 100 thì số sinh viên bị ảnh hưởng đều bằng nhau. Trọng số nhỏ hơn chỉ cho phép solver đảo thêm chính những sinh viên vốn đã bị ảnh hưởng để giảm $Z$.

#### Cách giải

- Luôn giải một lần (single), vì lời giải gợi ý cần đủ cả bốn nhóm biến. Giới hạn thời gian là `reschedule.time_limit_sec`, mặc định 45 giây, tính chung cho cả hai bước dưới đây và cả thời gian dựng mô hình, để tổng thời gian dưới 1 phút với bộ `large`.
- Bước 1, xếp lại cục bộ. Gọi $C^{*}$ là tập môn có lượt trong lịch cũ không còn hợp lệ: lượt dùng một phòng, hoặc có một giám thị, đang bận ở một ca mà lượt đó chiếm (lịch bận đã gồm sự cố). Các môn ngoài phạm vi được cố định đúng như lịch cũ: mọi biến $x$, $u$, $q$ của môn đó, và mọi biến $w$ của các (phòng, ca) mà lượt của môn đó chiếm, đều bằng giá trị cũ. Phạm vi lần lượt là: $C^{*}$; $C^{*}$ cộng mọi môn có lượt vào ngày có sự cố hoặc ngày của các lượt trong $C^{*}$; toàn bộ lịch. Dừng ở phạm vi đầu tiên có lời giải. Mô hình còn rất ít biến tự do nên giải trong vài giây, và phần lịch không liên quan chắc chắn không bị xáo trộn.
- Bước 2. Với thời gian còn lại, giải trên toàn lịch, gợi ý (`AddHint` của CP-SAT) bằng lời giải bước 1, hoặc bằng lịch cũ nếu bước 1 không có lời giải. Lời giải bước 2 chỉ được dùng khi hàm mục tiêu khi xếp lại (Z cộng điểm phạt thay đổi) thấp hơn bước 1. Vì vậy kết quả không bao giờ kém lời giải cục bộ, và khi giải được hết (ví dụ `toy`) vẫn đạt tối ưu trên toàn lịch.
- Lý do có bước 1: chỉ dùng gợi ý thì khi lịch cũ vi phạm nhiều ràng buộc cùng lúc, CP-SAT có thể không sửa từ gợi ý được. Với ba sự cố cùng lúc trên `large`, trong 45 giây CP-SAT trả về một lịch đổi 77 lượt và ảnh hưởng 985 trong 1000 sinh viên (A.13).
- Trạng thái: lời giải của bước 1 chỉ tối ưu trong phạm vi đã mở lại nên được báo `FEASIBLE`. Chỉ bước 2 mới có thể báo `OPTIMAL` hoặc kết luận `INFEASIBLE`. Các bước được ghi trong thông báo I04.
- Lịch cũ phải khớp dữ liệu: cùng môn, cùng danh sách sinh viên, cùng phòng và ca. Thêm môn hoặc thêm sinh viên sau khi công bố lịch nằm ngoài phạm vi của phiên bản này.
- Nếu vô nghiệm (ví dụ sự cố làm mất phòng máy duy nhất), chạy chẩn đoán như ở A.8.

#### Kết quả

`objective` vẫn là $Z$ của lịch mới, để so trực tiếp với lịch cũ. `best_bound` là `null` vì cận dưới của solver gồm cả điểm phạt thay đổi. File kết quả có thêm `changes` (từng lượt bị đổi) và `reschedule` (sự cố, $R_1..R_4$, tóm tắt số lượt, sinh viên và giám thị bị ảnh hưởng), xem data_schema mục 7.6.

Số sinh viên và giám thị bị ảnh hưởng không lấy từ $R_3$, $R_4$ mà được đếm bằng cách so sánh trực tiếp hai lịch: sinh viên bị ảnh hưởng khi ngày, ca hoặc phòng thi của mình đổi; giám thị bị ảnh hưởng khi tập (ngày, ca, phòng) coi thi của mình đổi. Các lượt được ghép theo từng môn, không theo `sitting_id`, nên một lượt bị dời ca hiện là "dời ca" chứ không phải một lượt bị xóa cộng một lượt mới.

Ở ví dụ trong data_schema mục 7.6 (bộ `toy`, phòng máy hỏng), $R_3 = 17$ nhưng chỉ 11 sinh viên bị ảnh hưởng: 11 sinh viên của lượt INT3306 bị dời được tính vào $R_3$, và 6 lần chuyển còn lại là chính một số sinh viên này được đổi sang lượt khác của INT2211 để giảm $Z$. CP-SAT chạy nhiều luồng nên các lần chạy có thể cho lịch hơi khác nhau với cùng giá trị mục tiêu.

Kết quả đo (8 luồng, cấu hình mặc định). Lịch cũ của `toy` là kết quả tham chiếu; lịch cũ của `medium` là lịch hai pha với giới hạn 300 giây ($Z$ = 11586):

| Bộ | Sự cố | Kết quả | Thời gian giải |
|---|---|---|---|
| `toy` | Phòng máy G2-LAB1 hỏng ca 3 ngày 15/12 | `OPTIMAL`, không vi phạm, 1 lượt dời ca, 11 sinh viên và 3 giám thị bị ảnh hưởng, $Z$ từ 2391 lên 2601 | 0,3 giây |
| `toy` | Giảng viên GV02 bận cả ngày 15/12 | `OPTIMAL`, không vi phạm, chỉ đổi giám thị của 2 lượt, $Z$ giữ 2391 | 0,2 giây |
| `toy` | Không có sự cố | `OPTIMAL`, lịch giữ nguyên | 0,2 giây |
| `medium` | Phòng máy E3-LAB2 hỏng ca 1 ngày 14/12, phòng G2-103 hỏng cả ngày 14/12 | `FEASIBLE`, không vi phạm, 2 lượt đổi phòng, không lượt nào dời ca, 68 sinh viên và 5 giám thị bị ảnh hưởng, $Z$ giữ 11586 | 45 giây (tổng 50 giây) |
| `medium` | Giảng viên GV01 bận cả ngày 14/12 | `OPTIMAL`, không vi phạm, chỉ đổi giám thị, $Z$ giữ 11586 | 39 giây (tổng 43 giây) |

Hai dòng `medium` ở bảng trên được đo trước khi có bước 1. Kết quả đo sau khi có bước 1, trên `medium` và `large`, nằm ở `experiments/README.md` (mục 5 và 6.4).

---

## B. Bài toán lịch phòng học/phòng máy

### B.1. Ý tưởng chính

Mô hình trả lời một câu hỏi: mỗi buổi học của mỗi lớp học phần diễn ra ở ca nào trong tuần, tại phòng nào.

So với bài toán A, bài toán B đơn giản hơn nhiều:

- Không có sinh viên cụ thể. Lịch học được xếp trước khi sinh viên đăng ký, nên trùng lịch được kiểm tra theo nhóm sinh viên (khóa và ngành), không theo từng người (scope mục 4.4).
- Không có giám thị. Giảng viên của mỗi lớp đã biết trước, mô hình chỉ cần đảm bảo giảng viên không dạy hai nơi cùng lúc.
- Mỗi buổi chiếm đúng 1 ca và 1 phòng. Không có buổi 2 ca, không chia lớp ra nhiều phòng.

Vì vậy chỉ cần một nhóm biến chính: lớp $k$ có học ở phòng $r$, ca $t$ hay không. Các buổi của cùng một lớp không được đánh số "buổi 1, buổi 2" mà chỉ hỏi "lớp có học ở ca $t$ hay không", cùng lý do như A.1: không sinh ra lời giải đối xứng.

Phần dùng lại từ bài toán A: khung 4 ca/ngày (scope mục 4.2), file phòng và file giảng viên, cách trình bày mô hình, trạng thái lời giải, cách báo lỗi, validator độc lập, chẩn đoán khi vô nghiệm và cách xếp lại khi có sự cố.

### B.2. Tập hợp và chỉ số

| Ký hiệu | Ý nghĩa |
|---|---|
| $W$ | Tập ngày học trong tuần (Thứ 2 đến Thứ 7), chỉ số $d$ |
| $T$ | Tập các ca học dùng được trong tuần, chỉ số $t$. Tối đa 6 × 4 = 24 ca |
| $T_d \subseteq T$ | Các ca thuộc ngày $d$ |
| $K$ | Tập lớp học phần, chỉ số $k$. Lớp lý thuyết và lớp thực hành của cùng một học phần là hai lớp khác nhau |
| $K^{M}, K^{V}$ | Lớp cần phòng máy, lớp học phòng thường. $K = K^{M} \cup K^{V}$, hai tập không giao nhau |
| $R$ | Tập phòng, chỉ số $r$ |
| $R^{V}, R^{M}$ | Phòng thường, phòng máy, như bài toán A |
| $R_k$ | Phòng phù hợp với lớp $k$: đúng loại và đủ chỗ (xem B.3) |
| $G$ | Tập giảng viên có ít nhất một lớp, chỉ số $g$ |
| $K_g \subseteq K$ | Các lớp do giảng viên $g$ dạy |
| $H$ | Tập nhóm sinh viên, chỉ số $h$. Mỗi nhóm là một khóa của một ngành, ví dụ K67 ngành Công nghệ thông tin |
| $K_h \subseteq K$ | Các lớp bắt buộc của nhóm $h$ |

Một nhóm sinh viên học chung mọi lớp bắt buộc của mình. Nếu một khóa của một ngành đông đến mức phải tách thành nhiều lớp song song, mỗi phần tách ra là một nhóm riêng (ví dụ K67-CN1 và K67-CN2), và mỗi nhóm được gắn với lớp song song mà nhóm đó học.

### B.3. Tham số

| Ký hiệu | Ý nghĩa | Ghi chú |
|---|---|---|
| $n_k$ | Sĩ số dự kiến của lớp $k$ | Số nguyên $\ge 1$ |
| $h_k$ | Số buổi mỗi tuần của lớp $k$ | Số nguyên $\ge 1$ |
| $g(k)$ | Giảng viên dạy lớp $k$ | Mỗi lớp đúng một giảng viên |
| $\sigma_r$ | Sức chứa khi học của phòng $r$ | Số ghế với phòng thường, số máy đang hoạt động với phòng máy. Khác $\kappa_r$ của bài toán A: khi học không cần ngồi giãn cách |
| $B^{R}_r \subseteq T$ | Các ca trong tuần phòng $r$ bận (bảo trì, sự kiện định kỳ) | |
| $B^{G}_g \subseteq T$ | Các ca trong tuần giảng viên $g$ bận | |
| $A_g \subseteq T$ | Các ca giảng viên $g$ không muốn dạy | Nguyện vọng, dùng cho B-S2. Khác $B^{G}_g$: ca bận là cấm, ca không muốn chỉ bị phạt |
| $\rho$ | Ngưỡng sử dụng phòng máy | Mặc định 0,85 (B-S4) |
| $\beta_1, \dots, \beta_4$ | Trọng số các ràng buộc mềm | Số nguyên, xem B.6 |

Từ các tham số trên, định nghĩa các tập dẫn xuất:

- Phòng phù hợp với lớp $k$, gồm cả B-H3 (đủ chỗ) và B-H4 (đúng loại):

$$
R_k =
\begin{cases}
\{\, r \in R^{M} : \sigma_r \ge n_k \,\} & \text{nếu } k \in K^{M} \\
\{\, r \in R^{V} : \sigma_r \ge n_k \,\} & \text{nếu } k \in K^{V}
\end{cases}
$$

- Ca lớp $k$ có thể học ở phòng $r$, gồm B-H5 (ca bận của giảng viên) và B-H6 (ca bận của phòng):

$$
T_{k,r} = T \setminus \big( B^{R}_r \cup B^{G}_{g(k)} \big)
$$

- Số phòng máy dùng được ở ca $t$, và số phòng máy tối đa nên dùng ở ca đó:

$$
m_t = \big\lvert \{\, r \in R^{M} : t \notin B^{R}_r \,\} \big\rvert, \qquad \bar{m}_t = \lfloor \rho \, m_t \rfloor
$$

Lớp học phòng thường không được xếp vào phòng máy, dù phòng máy còn trống. Lý do: phòng máy là nguồn lực khan hiếm, có kỹ thuật viên phụ trách và cần thời gian bảo trì (scope mục 2). Nếu nhóm muốn cho phép, chỉ cần đổi định nghĩa $R_k$ của $K^{V}$ thành $R^{V} \cup R^{M}$; các công thức còn lại giữ nguyên.

### B.4. Biến quyết định

| Biến | Miền | Ý nghĩa |
|---|---|---|
| $y_{k,r,t}$ | $\{0,1\}$, với $k \in K,\ r \in R_k,\ t \in T_{k,r}$ | Bằng 1 nếu lớp $k$ có một buổi học ở phòng $r$, ca $t$ |
| $e_{k,d}$ | Số nguyên $\ge 0$ | Biến phụ cho B-S3 |
| $v_t$ | Số nguyên $\ge 0$ | Biến phụ cho B-S4 |

Biến $y$ chỉ được tạo với phòng phù hợp và ca không bận. Vì vậy B-H3, B-H4, B-H6 và phần "không xếp vào ca bận" của B-H5 được đảm bảo ngay từ cách khai báo biến.

Biểu thức dùng để viết gọn:

- Lớp $k$ có học ở ca $t$ hay không:

$$
z_{k,t} = \sum_{r \in R_k : t \in T_{k,r}} y_{k,r,t}
$$

- Số phòng máy đang dùng ở ca $t$:

$$
M_t = \sum_{k \in K^{M}} \ \sum_{r \in R_k : t \in T_{k,r}} y_{k,r,t}
$$

### B.5. Ràng buộc cứng

#### B-H1. Đủ số buổi mỗi tuần

$$
\sum_{r \in R_k} \ \sum_{t \in T_{k,r}} y_{k,r,t} = h_k \qquad \forall k \in K
$$

#### B-H2. Mỗi phòng, mỗi ca tối đa một lớp

$$
\sum_{k \in K : r \in R_k,\ t \in T_{k,r}} y_{k,r,t} \le 1 \qquad \forall r \in R,\ t \in T
$$

#### B-H3. Đủ chỗ, và B-H4. Lớp thực hành vào phòng máy

Đảm bảo bằng miền của biến $y$: $y_{k,r,t}$ chỉ tồn tại khi $r \in R_k$, tức phòng đúng loại và $\sigma_r \ge n_k$.

#### B-H5. Giảng viên không dạy hai lớp cùng ca, không dạy vào ca bận

$$
\sum_{k \in K_g} z_{k,t} \le 1 \qquad \forall g \in G,\ t \in T
$$

Phần ca bận được đảm bảo bằng miền của biến: $T_{k,r}$ đã loại $B^{G}_{g(k)}$.

Vì mỗi lớp chỉ có một giảng viên, ràng buộc này cũng suy ra $z_{k,t} \le 1$: một lớp không có hai buổi cùng ca ở hai phòng khác nhau. Không cần viết riêng ràng buộc đó.

#### B-H6. Không xếp vào ca phòng đã báo bận

Đảm bảo bằng miền của biến: $T_{k,r}$ đã loại $B^{R}_r$.

#### B-H7. Các lớp bắt buộc của cùng một nhóm không trùng ca

$$
\sum_{k \in K_h} z_{k,t} \le 1 \qquad \forall h \in H,\ t \in T
$$

Chỉ áp dụng cho lớp bắt buộc. Lớp tự chọn không gắn với nhóm nào nên có thể trùng ca với lớp bắt buộc; sinh viên chọn lớp tự chọn sau khi đã có lịch.

### B.6. Ràng buộc mềm và hàm mục tiêu

#### B-S1. Lãng phí chỗ

Số chỗ trống của mỗi buổi học:

$$
P^{B}_1 = \sum_{k \in K} \ \sum_{r \in R_k} \ \sum_{t \in T_{k,r}} (\sigma_r - n_k) \, y_{k,r,t}
$$

Hệ số $\sigma_r - n_k \ge 0$ nhờ định nghĩa $R_k$, và là hằng số, nên không cần biến phụ.

#### B-S2. Tôn trọng nguyện vọng giờ dạy của giảng viên

Số buổi xếp vào ca giảng viên không muốn dạy:

$$
P^{B}_2 = \sum_{k \in K} \ \sum_{t \in A_{g(k)}} z_{k,t}
$$

#### B-S3. Các buổi của cùng một lớp không nằm cùng ngày

$$
e_{k,d} \ge \sum_{t \in T_d} z_{k,t} - 1, \quad e_{k,d} \ge 0 \qquad \forall k \in K,\ d \in W
$$

$$
P^{B}_3 = \sum_{k \in K} \sum_{d \in W} e_{k,d}
$$

$e_{k,d}$ là số buổi "thừa" của lớp $k$ trong ngày $d$, cách đếm giống A-S1. Lớp có $h_k$ lớn hơn số ngày học được bắt buộc phải có ít nhất $h_k - \lvert W \rvert$ buổi thừa. Phần này là hằng số với mọi lời giải nên không ảnh hưởng đến việc chọn lịch; bước kiểm tra trước báo thông tin PB6 (B.7).

#### B-S4. Giữ hệ số sử dụng phòng máy không quá $\rho$

Ở mỗi ca, số phòng máy đang dùng không nên vượt $\bar{m}_t = \lfloor \rho \, m_t \rfloor$:

$$
v_t \ge M_t - \bar{m}_t, \quad v_t \ge 0 \qquad \forall t \in T
$$

$$
P^{B}_4 = \sum_{t \in T} v_t
$$

Ràng buộc được tính theo từng ca, không theo tổng cả tuần. Lý do: tổng số buổi cần phòng máy trong tuần $\sum_{k \in K^{M}} h_k$ đã cố định theo dữ liệu, nên hệ số sử dụng tính trên cả tuần là hằng số, mô hình không thay đổi được. Điều mô hình thay đổi được là dàn đều các buổi thực hành sang các ca khác nhau, để ca nào cũng còn phòng máy trống. Đó cũng là ý nghĩa "dự phòng" trong scope: khi một phòng máy hỏng ở ca $t$, lớp của phòng đó có thể chuyển sang phòng máy còn trống ngay trong ca $t$ mà không phải dời giờ (B.9).

Ví dụ: có 4 phòng máy thì $\bar{m}_t = \lfloor 3{,}4 \rfloor = 3$, tức mỗi ca nên chừa ít nhất 1 phòng máy. Có 1 phòng máy thì $\bar{m}_t = 0$, mọi buổi thực hành đều bị phạt; vì số buổi thực hành cố định nên phần phạt này là hằng số.

Hệ số sử dụng tính trên cả tuần vẫn được báo trong KPI, và được kiểm tra trước khi giải (PB7 ở B.7).

#### Hàm mục tiêu

$$
\min \ Z^{B} = \beta_1 P^{B}_1 + \beta_2 P^{B}_2 + \beta_3 P^{B}_3 + \beta_4 P^{B}_4
$$

Trọng số mặc định, số nguyên:

| Trọng số | Giá trị | Đơn vị của $P^{B}_k$ | Lý do |
|---|---|---|---|
| $\beta_1$ (B-S1) | 1 | Chỗ trống × buổi | Đơn vị nhỏ nhất, dùng làm mốc, như A-S4 |
| $\beta_2$ (B-S2) | 50 | Buổi vào ca giảng viên không muốn dạy | Chỉ chấp nhận khi đổi lại tiết kiệm được ít nhất 50 chỗ trống |
| $\beta_3$ (B-S3) | 100 | Buổi thừa trong ngày của một lớp | Ảnh hưởng tới cả lớp sinh viên và giảng viên, nên nặng hơn B-S2 |
| $\beta_4$ (B-S4) | 30 | Phòng máy dùng vượt ngưỡng ở một ca | Mất dự phòng ở một ca, ngang 30 chỗ trống |

Cách đọc: xếp hai buổi của một lớp vào cùng ngày (tốn 100) chỉ đáng khi tránh được hai buổi dạy vào ca giảng viên không muốn (2 × 50). Các trọng số này là điểm khởi đầu; phần thực nghiệm phân tích độ nhạy như bài toán A.

### B.7. Kiểm tra dữ liệu trước khi giải

Các kiểm tra sau chạy trước khi dựng mô hình. Mã PB để không nhầm với mã P của bài toán A.

| Mã | Điều kiện | Mức độ |
|---|---|---|
| PB1 | Có lớp $R_k = \emptyset$: không phòng nào đúng loại và đủ chỗ | Lỗi, dừng |
| PB2 | Có lớp có ít hơn $h_k$ ca dùng được, tức $\lvert \bigcup_{r \in R_k} T_{k,r} \rvert < h_k$ | Lỗi, dừng |
| PB3 | Có giảng viên dạy nhiều buổi hơn số ca rảnh: $\sum_{k \in K_g} h_k > \lvert T \setminus B^{G}_g \rvert$ | Lỗi, dừng |
| PB4 | Có nhóm có nhiều buổi bắt buộc hơn số ca: $\sum_{k \in K_h} h_k > \lvert T \rvert$ | Lỗi, dừng |
| PB5 | Tổng số buổi cần phòng máy lớn hơn tổng số (phòng máy, ca) không bận; tương tự với phòng thường | Lỗi, dừng |
| PB6 | Có lớp $h_k > \lvert W \rvert$ | Thông tin: B-S3 không thể bằng 0 với lớp này |
| PB7 | Hệ số sử dụng phòng máy cả tuần, $\sum_{k \in K^{M}} h_k \big/ \sum_{t \in T} m_t$, lớn hơn $\rho$ | Cảnh báo: không thể chừa phòng máy dự phòng ở mọi ca, $P^{B}_4$ chắc chắn lớn hơn 0 |

Cũng như A.8, các kiểm tra này là điều kiện cần, chưa phải điều kiện đủ. Khi CP-SAT trả về `INFEASIBLE`, chạy chẩn đoán với ba nhóm ràng buộc được thử bỏ:

| Nhóm | Ràng buộc bị bỏ | Nếu bỏ nhóm này mà có lịch, nghĩa là |
|---|---|---|
| Giảng viên | B-H5, kể cả ca bận của giảng viên | Giảng viên dạy quá nhiều lớp hoặc bận quá nhiều ca |
| Nhóm sinh viên | B-H7 | Một nhóm có quá nhiều lớp bắt buộc so với số ca, khi tính cả các ràng buộc khác |
| Phòng bận | B-H6 | Phòng bận quá nhiều ca |

Thông báo dùng lại mã N01–N05 như bài toán A.

### B.8. Chiến lược giải và hậu xử lý

Giải toàn bộ mô hình một lần bằng CP-SAT, cùng giới hạn thời gian và cùng bốn trạng thái như A.7. Không cần chiến lược hai pha vì mô hình nhỏ. Ước lượng giới hạn trên của số biến $y$ (số lớp × số phòng × số ca; 24 ca, riêng `toy_b` 22 ca):

| Bộ dữ liệu | Lớp | Phòng | Biến $y$ (xấp xỉ, trước khi lọc theo loại và sức chứa) |
|---|---|---|---|
| `toy_b` | 10 | 4 | 880 (thực tế 303, B.12) |
| `medium` | 60 | 10 | 14 nghìn |
| `large` | 120 | 15 | 43 nghìn |

Số biến thật nhỏ hơn nhiều, vì mỗi lớp chỉ có biến với phòng đúng loại và đủ chỗ. Ví dụ lớp thực hành chỉ có biến với 3–4 phòng máy.

Hậu xử lý đơn giản hơn A.10, vì không có sinh viên cụ thể và không có giám thị:

1. Mỗi biến $y_{k,r,t} = 1$ thành một buổi học trong file kết quả (data_schema mục 9).
2. Tính KPI.
3. Chạy validator độc lập: kiểm tra lại B-H1 đến B-H7 trên lịch cuối cùng, báo vi phạm theo mã.

### B.9. Xếp lại khi có sự cố

Dùng cùng cách tiếp cận như A.14. Có hai loại sự cố:

- Phòng hoặc giảng viên bận thêm một ca hoặc cả một ngày trong tuần, có dạng một dòng của file ca bận tuần. Sự cố được thêm vào $B^{R}_r$ hoặc $B^{G}_g$.
- Thêm lớp mới, đúng mục "thêm lớp → xếp lại" trong scope mục 5. Lớp mới có trong dữ liệu nhưng không có trong lịch cũ.

Gọi $\bar{Y}$ là tập các bộ $(k, r, t)$ có $y_{k,r,t} = 1$ trong lịch cũ, và $\bar{T}_k$ là tập ca học cũ của lớp $k$. Biến không còn tồn tại được coi là bằng 0.

| Mã | Đếm | Công thức |
|---|---|---|
| B-R1 | Buổi học cũ bị dời sang ca khác | $R^{B}_1 = \sum_{k} \sum_{t \in \bar{T}_k} (1 - z_{k,t})$ |
| B-R2 | Buổi học cũ giữ ca nhưng đổi phòng | $R^{B}_2 = \sum_{(k,r,t) \in \bar{Y}} (z_{k,t} - y_{k,r,t})$ |

Mỗi số hạng của $R^{B}_2$ bằng 0 hoặc 1 vì $y_{k,r,t} \le z_{k,t} \le 1$. Buổi bị dời ca đã tính ở B-R1 nên không bị tính thêm ở B-R2. Lớp mới không có buổi cũ nên không bị phạt thay đổi.

Hàm mục tiêu khi xếp lại là $Z^{B} + \gamma_1 R^{B}_1 + \gamma_2 R^{B}_2$, mặc định $\gamma_1 = 100$, $\gamma_2 = 20$. Dời ca phải báo cho cả lớp và giảng viên, có thể làm trùng với lịch khác của sinh viên; đổi phòng chỉ cần báo địa điểm mới.

Cách giải giống A.14: bước 1 chỉ mở lại các lớp có buổi không còn hợp lệ (và lớp mới), các lớp khác cố định như lịch cũ; nếu không có lời giải thì mở rộng sang các lớp cùng ngày, rồi toàn bộ lịch. Bước 2 giải trên toàn lịch với gợi ý từ bước 1 và chỉ dùng khi tốt hơn. Nhờ B-S4, thường có phòng máy trống ngay trong ca bị ảnh hưởng nên lớp chỉ phải đổi phòng.

### B.10. Đối chiếu với 10 quy tắc lập mô hình của Daskin

| Quy tắc | Áp dụng trong mô hình |
|---|---|
| 1. Định nghĩa rõ mọi tập hợp bằng lời | Bảng B.2 |
| 2. Tách bạch tập hợp, đầu vào, biến quyết định | Ba bảng riêng B.2, B.3, B.4 |
| 3. Có chỉ số trong ký hiệu thì có trong lời định nghĩa | Mọi ký hiệu có chỉ số đều nêu chỉ số trong cột ý nghĩa |
| 4. Không để chỉ số lơ lửng trong hàm mục tiêu | Mọi chỉ số trong $P^{B}_1, \dots, P^{B}_4$ đều nằm dưới một dấu tổng |
| 5. Mục tiêu và mỗi ràng buộc chứa biến quyết định | Đã kiểm tra từng công thức |
| 6. Mọi nhóm biến phải liên kết với nhau | $e$ và $v$ nối với $y$ qua $z_{k,t}$ và $M_t$ |
| 7. Mỗi chỉ số hoặc lấy tổng hoặc "với mọi", không cả hai | Đã kiểm tra từng công thức |
| 8. Giữ mô hình tuyến tính | Mọi ràng buộc tuyến tính; hệ số chỗ trống $\sigma_r - n_k$ là hằng số |
| 9. Tránh big-M | Không dùng |
| 10. Tách nhỏ ràng buộc | B-H5 và B-H7 viết cho từng (giảng viên hoặc nhóm, ca) thay vì gộp theo ngày |

### B.11. Những điều mô hình cố ý không xét

- Không kiểm tra trùng lịch theo từng sinh viên, và không xét lớp tự chọn trùng ca với lớp bắt buộc (scope mục 4.4).
- Không bắt các buổi của một lớp học cùng một phòng. Lớp có thể học các buổi khác nhau ở các phòng khác nhau, miễn đúng loại và đủ chỗ.
- Không xét buổi học dài hơn 1 ca. Lớp thực hành cần 2 ca liền nhau được khai báo bằng 2 buổi; mô hình có thể xếp hai buổi này ở hai ngày khác nhau.
- Không giới hạn số buổi dạy của một giảng viên trong một ngày.
- Không xét thời gian di chuyển giữa các tòa nhà của sinh viên và giảng viên.
- Lịch tuần lặp lại giống nhau cả học kỳ; không xét tuần nghỉ lễ hay tuần thi giữa kỳ.

### B.12. Kiểm chứng đặc tả

Kiểm chứng giống A.13: một bản cài đặt thử với OR-Tools CP-SAT 9.15, viết đúng theo các công thức B.3 đến B.7, cùng một bộ kiểm tra viết độc lập. Bộ kiểm tra tự đọc file CSV, không dùng lại công thức của mô hình, mà soát lịch trực tiếp theo luật trong scope (đếm số lớp theo từng phòng và ca, từng giảng viên và ca, từng nhóm và ca), rồi tự tính lại các điểm phạt.

Dữ liệu thử là bộ `data/toy_b` (mô tả trong `data/toy_b/README.md`): 10 lớp, 4 phòng (2 phòng máy), 3 nhóm sinh viên, 22 ca, có phòng bận, giảng viên bận và ca giảng viên không muốn dạy. Mỗi lớp được chọn để kiểm thử một tình huống.

| Kịch bản | Kết quả mong đợi | Kết quả |
|---|---|---|
| `toy_b`, trọng số mặc định, chạy 3 lần | Tối ưu, không vi phạm | `OPTIMAL`, $Z$ = 355 cả 3 lần, dưới 0,1 giây; không vi phạm; điểm phạt tính lại độc lập khớp với solver |
| 6 biến thể vô nghiệm: lớp lý thuyết hoặc lớp thực hành không vừa phòng nào, giảng viên gần như bận cả tuần, giảng viên quá tải, nhóm quá tải, quá nhiều buổi thực hành | Kiểm tra trước phát hiện đúng mã; mô hình vô nghiệm | Phát hiện đúng PB1 (2 biến thể), PB2, PB3, PB4, PB5; cả 6 biến thể mô hình đều `INFEASIBLE` |
| Hệ số sử dụng phòng máy cả tuần 0,875 | Cảnh báo PB7, vẫn có lịch, $P^{B}_4 > 0$ | PB7; `OPTIMAL`, không vi phạm, $P^{B}_4$ = 17 |
| Cố ý làm hỏng lời giải tối ưu theo 7 cách, mỗi cách vi phạm một ràng buộc từ B-H1 đến B-H7 | Bộ kiểm tra phải phát hiện | 7/7 phát hiện đúng mã |
| Tăng $\beta_2$ lên 150 (đắt hơn một buổi thừa trong ngày) | Không dạy vào ca GV05 không muốn, chấp nhận dồn buổi | $P^{B}_2$ từ 1 xuống 0, $P^{B}_3$ từ 2 lên 3 |
| Tắt B-S4 ($\beta_4 = 0$) | Solver không còn chừa phòng máy dự phòng | $P^{B}_4$ từ 1 lên 2: có ca dùng cả hai phòng máy |
| 8 bộ ngẫu nhiên (12 lớp, giảng viên và nhóm ngẫu nhiên) | Không vi phạm | 6 bộ `OPTIMAL`, không vi phạm, điểm phạt khớp; 2 bộ còn lại bị PB3 phát hiện trước khi giải và mô hình cũng `INFEASIBLE` |
| Lớp ELT2035 (7 buổi) và INT3306-TH (6 buổi) cùng nhóm, hai giảng viên đều chỉ rảnh Thứ 2–4 (12 ca) | Qua mọi kiểm tra PB nhưng vô nghiệm; chẩn đoán chỉ ra nguyên nhân | Không mã PB nào báo lỗi; `INFEASIBLE`. Bỏ nhóm giảng viên hoặc bỏ B-H7 thì có lịch, bỏ phòng bận thì vẫn vô nghiệm, tức chẩn đoán báo hai N01 |

Đáp án tham chiếu: trên `data/toy_b` với trọng số mặc định, giá trị mục tiêu tối ưu là 355 ($P^{B}_1$ = 75, $P^{B}_2$ = 1, $P^{B}_3$ = 2, $P^{B}_4$ = 1). Kiểm thử của `room_solver.py` dùng con số này, như 2391 của bài toán A.

Mô hình trên `toy_b` có 303 biến $y$, ít hơn nhiều so với giới hạn trên 10 × 4 × 22 = 880, vì mỗi lớp chỉ có biến với phòng đúng loại, đủ chỗ và ca không bận.

Phần xếp lại khi có sự cố (B.9) chưa được kiểm chứng bằng bản cài đặt thử; sẽ kiểm chứng khi cài đặt, dựa trên code xếp lại của bài toán A.
