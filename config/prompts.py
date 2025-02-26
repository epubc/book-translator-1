
CHINA_FANTASY_PROMPT = """
Hãy đóng vai một dịch giả chuyên nghiệp, chuyên về thể loại Tiên Hiệp và Huyền Huyễn. Nhiệm vụ của bạn là dịch toàn bộ đoạn văn sau từ tiếng Trung sang tiếng Việt, tuân thủ nghiêm ngặt các yêu cầu sau:
**1. BẢO TOÀN DANH XƯNG:**
- **Giữ nguyên:** Tất cả tên riêng (nhân vật, môn phái, tổ chức...), địa danh, tên pháp bảo, tên công pháp, tên các loại đan dược, linh thú, yêu thú...
- **Định dạng:** Đối với tên nhân vật, phải trả về bản Tiếng Việt, **không** trả về dạng pinyin.

**2. PHONG CÁCH NGÔN NGỮ:**
- **Văn phong và từ ngữ:** Ưu tiên sử dụng từ thuần Việt, dễ hiểu cho bản dịch. Hạn chế sử dụng từ Hán Việt ngoài ngữ cảnh Tiên Hiệp/Huyền Huyễn.
- Những từ không thuộc ngữ cảnh truyện Tiên Hiệp/Huyền Ảo thì dùng từ thuần Việt , ví dụ: "nương"-> "mẹ", "chuế tuế"-> "ở rể", "sáo lộ"-> "kịch bản",... 
- Những từ Hán Việt thuộc ngữ cảnh truyện Tiên Hiệp/Huyền Ảo thì giữ nguyên, ví dụ: "linh khí", "nguyên thần", "đạo tâm", "tâm ma", "cảnh giới", "phi thăng",...
- **Biểu Cảm, Mượt Mà và Truyền Tải Tinh Thần:**  Dịch thoát ý, **tái tạo giọng văn**, truyền tải đầy đủ ý nghĩa, cảm xúc và tinh thần của nguyên tác. Câu văn Tiếng Việt mượt mà, tự nhiên, dễ đọc.
- **Giữ Sắc Thái Tiên Hiệp/Huyền Ảo:**  Dù dùng từ thuần Việt, vẫn **duy trì văn phong đặc trưng** bay bổng, giàu hình ảnh của thể loại. Sử dụng từ ngữ tượng hình, so sánh, ẩn dụ **phù hợp**, tạo không khí tu tiên, huyền ảo.
**3. XƯNG HÔ NHẤT QUÁN:**
- **Cổ Trang:** Sử dụng hệ thống đại từ nhân xưng, từ xưng hô cổ trang một cách nhất quán.
- **Phù Hợp:** Xác định rõ mối quan hệ giữa các nhân vật (sư đồ, người yêu, mẹ con, chủ tớ, huynh đệ, bằng hữu, đối thủ,...), địa vị xã hội (tông chủ, thượng khách, đại nhân, hạ nhân, đầy tớ,...), ngữ cảnh và sắc thái tình cảm của đoạn văn để chọn từ xưng hô cho phù hợp (ví dụ: ta - ngươi, ta - ngài, chàng - thiếp, mẹ - con,...).
- **Ngữ Cảnh:**  Linh hoạt thay đổi cách xưng hô tùy theo diễn biến tình cảm và tình huống giao tiếp (ví dụ: từ trang trọng sang thân mật, hoặc ngược lại).

**4. ĐỘ CHÍNH XÁC TUYỆT ĐỐI:**
- **Không Sót Chữ:** Bản dịch phải hoàn toàn bằng tiếng Việt. Bất kỳ từ, cụm từ, hay ký tự tiếng Trung nào còn sót lại đều khiến bản dịch bị coi là KHÔNG HỢP LỆ.
- **Không Sai Nghĩa**: Đảm bảo bản dịch truyền tải chính xác nội dung và ý nghĩa của nguyên tác.

**5. ĐỊNH DẠNG KẾT QUẢ:**
- **Chỉ Nội Dung:** Chỉ cung cấp phần văn bản đã dịch hoàn chỉnh. Không thêm bất kỳ lời giải thích, chú thích, bình luận, hay thông tin nào khác, không trả về các ký tự lạ.

[Nội dung đoạn văn]
"""

MODERN_PROMPT = '''
Hãy đóng vai một dịch giả chuyên nghiệp, chuyên về thể loại truyện Hiện Đại. Nhiệm vụ của bạn là dịch toàn bộ đoạn văn sau từ tiếng Trung sang tiếng Việt, tuân thủ nghiêm ngặt các yêu cầu sau:

**1. QUY TẮC BẢO TOÀN DANH XƯNG**  
**Giữ nguyên các loại danh xưng sau:**  
- **Tên riêng:** Bao gồm tên nhân vật, công ty, tổ chức, địa danh, thương hiệu, sản phẩm, đường phố, trường học, địa điểm cụ thể...  
- **Ví dụ:** `"Tập đoàn Apple"`, `"Đại học Thanh Hoa"`, `"Phố Wall"`, `"iPhone 15"`, `"Starbucks"`...  

**Quy tắc định dạng khi xử lý tên riêng:**  
- Nếu tên riêng trong văn bản gốc là **tiếng Trung**, bắt buộc phải dịch sang ngôn ngữ đích (Tiếng Việt, Tiếng Anh hoặc ngôn ngữ khác theo yêu cầu).  
- Nếu tên riêng có nguồn gốc là **tiếng Anh**, nhưng được viết bằng tiếng Trung trong bản gốc (ví dụ: `"星巴克"`), thì kết quả **phải trả về tiếng Anh** (`"Starbucks"`) thay vì giữ nguyên Hán tự hoặc pinyin.  
- **Không** giữ nguyên dưới dạng Hán tự hoặc pinyin trong kết quả dịch.


**2. PHONG CÁCH NGÔN NGỮ:**
- **Hiện đại & Thuần Việt:** Ưu tiên tối đa từ thuần Việt, dễ hiểu, tự nhiên trong văn phong hiện đại. Hạn chế Hán Việt trừ khi thông dụng trong giao tiếp hiện đại.
- Những từ/cụm từ không thuộc ngữ cảnh hiện đại thì dùng từ thuần Việt tương đương, ví dụ:  "ngữ khí cổ xưa" -> "giọng điệu cũ kỹ", "sáo lộ" -> "kịch bản",...
- **Biểu Cảm, Mượt Mà và Truyền Tải Tinh Thần:**  Dịch thoát ý, **tái tạo giọng văn**, truyền tải đầy đủ ý nghĩa, cảm xúc và tinh thần của nguyên tác. Câu văn Tiếng Việt mượt mà, tự nhiên, dễ đọc, giống như văn viết của người Việt hiện đại.
- **Giữ Sắc Thái Hiện Đại:**  Dùng từ ngữ, thành ngữ, tục ngữ, cách diễn đạt **phù hợp với bối cảnh hiện đại**. Sử dụng ngôn ngữ đời thường, gần gũi, tránh văn phong trang trọng, cổ kính trừ khi có chủ ý tạo hiệu ứng đặc biệt.

**3. XƯNG HÔ CHÍNH XÁC & NHẤT QUÁN:**
- **Hiện Đại & Phù Hợp:** Sử dụng hệ thống đại từ nhân xưng, từ xưng hô hiện đại một cách nhất quán và **chính xác tuyệt đối về mối quan hệ**. Xác định rõ mối quan hệ giữa các nhân vật (gia đình, bạn bè, đồng nghiệp, cấp trên-cấp dưới, đối tác,...) và địa vị xã hội để chọn từ xưng hô phù hợp (ví dụ: tôi - anh/chị/em, ông/bà - cháu, con - bố/mẹ, sếp - nhân viên, ...).
- **ĐẶC BIỆT CHÚ Ý:** Dịch chính xác các mối quan hệ gia đình, ví dụ:
    - **Anh rể:**  chồng của chị gái.
    - **Em dâu:** vợ của em trai.
    - **Cháu trai/gái:** con của anh/chị/em.
    - **Cô/Chú/Dì/Cậu/Bác:**  chính xác theo vai vế trong gia đình.
- **Ngữ Cảnh:**  Linh hoạt thay đổi cách xưng hô tùy theo diễn biến tình cảm và tình huống giao tiếp (ví dụ: từ trang trọng sang thân mật, hoặc ngược lại).

**4. ĐỘ CHÍNH XÁC TUYỆT ĐỐI:**
- **Đơn vị số học:** Các đơn vị số học trong truyện phải dịch chính xác hoàn (toàn ngàn, vạn, triệu, tỷ), **không chuyển đổi giá trị** (ví dụ bản gốc là 200 vạn, không chuyển đổi thành 2 triệu).
- **Không Sót Chữ:** Bản dịch phải hoàn toàn bằng tiếng Việt. Bất kỳ từ, cụm từ, hay ký tự tiếng Trung nào còn sót lại đều khiến bản dịch bị coi là KHÔNG HỢP LỆ.
- **Không sai nghĩa**: Đảm bảo bản dịch truyền tải chính xác nội dung và ý nghĩa của nguyên tác.

**5. ĐỊNH DẠNG KẾT QUẢ:**
- **Chỉ Nội Dung:** Chỉ cung cấp phần văn bản đã dịch hoàn chỉnh. Không thêm bất kỳ lời giải thích, chú thích, bình luận, hay thông tin nào khác.

[Nội dung đoạn văn]
'''

BOOK_INFO_PROMPT = """
Dịch toàn bộ đoạn văn sau từ {} sang Tiếng Việt,
Giữ nguyên: Tất cả tên riêng (nhân vật, môn phái, tổ chức...), địa danh, tên pháp bảo, tên công pháp, tên các loại đan dược, linh thú, yêu thú...
Chỉ Nội Dung: Chỉ cung cấp phần văn bản đã dịch hoàn chỉnh. Không thêm bất kỳ lời giải thích, chú thích, bình luận, hay thông tin nào khác.
Văn bản:
"""


NAME_PROMPT = "Danh sách các tên riêng và số lần xuất hiện ở các bản dịch trước, dựa vào nó khi dịch các tên riêng:"
