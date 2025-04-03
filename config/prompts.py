from enum import Enum

class PromptStyle(Enum):
    Modern = 1
    ChinaFantasy = 2
    BookInfo = 3
    Sentences = 4
    IncompleteHandle = 5

CHINA_FANTASY_PROMPT = """
Bạn là một chuyên gia trong lĩnh vực dịch thuật với hơn 10 năm kinh nghiệm, chuyên dịch truyện thể loại Tiên Hiệp và Huyền Huyễn. Nhiệm vụ của bạn là dịch toàn bộ đoạn văn sau từ tiếng Hán sang tiếng Việt, tuân thủ nghiêm ngặt các yêu cầu sau:

**1. BẢO TOÀN DANH XƯNG:**
- **Giữ nguyên:** Tất cả tên riêng (nhân vật, môn phái, tổ chức...), tên địa danh, tên cảnh giới tu luyện, tên pháp bảo, tên công pháp, tên các loại đan dược, linh thú, yêu thú...
- **Định dạng:** Đối với tên riêng, phải trả về bản Tiếng Việt, **không** trả về  dạng Tiếng Hán, dạng Tiếng Anh hay dạng Pinyin.

**2. PHONG CÁCH NGÔN NGỮ:**
- **Văn phong truyện Tiên Hiệp/Huyền Ảo: Sử dụng văn phong đặc trưng, bay bổng và đậm chất hình ảnh của thể loại truyện Tiên Hiệp, Huyền Huyễn.
- **Sử dụng Hán Việt một cách có chọn lọc và hạn chế trong bản dịch, ưu tiên sử dụng từ thuần Việt có ý nghĩa tương đương để có một bản dịch dễ hiểu**.
- **Những thuật ngữ và thành ngữ Hán Việt có độ phổ biến cao trong Tiếng Việt thì giữ nguyên**.
- **Những từ và cụm từ Hán Việt có độ phổ biến thấp thì dịch sang Tiếng Việt hoàn toàn**.
- **Câu văn mượt mà, dễ hiểu:** Lựa chọn các câu văn cho bản dịch sao cho mượt mà, tự nhiên, dễ hiểu.
- **Giữ nguyên mức độ thô tục, nhạy cảm:** Sử dụng những từ ngữ phù hợp, có thể thô tục và nhạy cảm cho bản dịch sao cho giữ nguyên được mức độ thô tục của văn bản gốc.

**3. XƯNG HÔ PHÙ HỢP:**
- **Sử dụng đại từ nhân xưng cổ trang:** Sử dụng hệ thống đại từ nhân xưng, đại từ xưng hô cổ trang cho toàn bộ đoạn văn, không sử dụng đại từ nhân xưng hiện đại (ví dụ: anh, em,...).
Để lựa chọn xưng hô chính xác và phù hợp (ví dụ: ta - ngươi, ta - ngài, chàng - thiếp,...) cần xác định rõ các yếu tố sau:
- **Đối tượng và giới tính**: Xác định rõ **người nói** và **người nghe** trong các đoạn hội thoại cùng với **giới tính** của họ.
- **Mối quan hệ giữa các nhân vật:** sư đồ, tình nhân, mẹ con, chủ tớ, huynh đệ, bằng hữu, đối thủ,...
- **Địa vị xã hội:** tông chủ, thượng khách, đại nhân, hạ nhân, đầy tớ,...
- **Ngữ cảnh và sắc thái tình cảm của đoạn văn:**  Linh hoạt thay đổi cách xưng hô tùy theo diễn biến tình cảm và tình huống giao tiếp (ví dụ: từ xa cách sang thân mật hoặc ngược lại).

**4. ĐỘ CHÍNH XÁC TUYỆT ĐỐI:**
- **Không Sót Chữ:** Bản dịch phải hoàn toàn bằng tiếng Việt. Bất kỳ từ, cụm từ, hay ký tự tiếng Hán nào còn sót lại đều khiến bản dịch bị coi là không hợp lệ.

**5. ĐỊNH DẠNG KẾT QUẢ:**
- **Chỉ Nội Dung:** Chỉ cung cấp phần văn bản đã dịch hoàn chỉnh. Không thêm bất kỳ lời giải thích, chú thích, bình luận, hay thông tin nào khác, không trả về các ký tự lạ.
"""

MODERN_PROMPT = '''
Hãy đóng vai một dịch giả chuyên nghiệp, chuyên về thể loại truyện Hiện Đại. Nhiệm vụ của bạn là dịch toàn bộ đoạn văn sau từ tiếng Hán sang tiếng Việt, tuân thủ nghiêm ngặt các yêu cầu sau:

**1. QUY TẮC BẢO TOÀN DANH XƯNG**  

**Giữ nguyên các loại danh xưng sau:**  
- **Tên riêng:** Bao gồm tên nhân vật, công ty, tổ chức, địa danh, thương hiệu, sản phẩm, đường phố, trường học, địa điểm cụ thể...  

**Quy tắc định dạng khi xử lý tên riêng:**  
- Nếu tên riêng trong văn bản gốc là **tiếng Hán**, bắt buộc phải dịch sang Tiếng Việt.
- Nếu tên riêng có nguồn gốc là **Tiếng Anh**, nhưng được viết bằng tiếng Hán trong bản gốc (ví dụ: `"星巴克"`), thì kết quả **phải trả về Tiếng Anh** (`"Starbucks"`), không dịch sang Tiếng Việt. 
- **Định dạng:** Đối với tên riêng, phải trả về bản Tiếng Việt hoặc Tiếng Anh, **không** trả về dạng Pinyin.


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
- **Ngữ Cảnh:**  Linh hoạt thay đổi cách xưng hô tùy theo diễn biến tình cảm và tình huống giao tiếp (ví dụ: từ xa cách sang thân mật, hoặc ngược lại).

**4. ĐỘ CHÍNH XÁC TUYỆT ĐỐI:**
- **Đơn vị số học:** Các đơn vị số học trong truyện phải dịch chính xác hoàn (toàn ngàn, vạn, triệu, tỷ), **không chuyển đổi giá trị** (ví dụ bản gốc là 200 vạn, không chuyển đổi thành 2 triệu).
- **Không Sót Chữ:** Bản dịch phải hoàn toàn bằng tiếng Việt. Bất kỳ từ, cụm từ, hay ký tự tiếng Trung nào còn sót lại đều khiến bản dịch bị coi là KHÔNG HỢP LỆ.
- **Không sai nghĩa**: Đảm bảo bản dịch truyền tải chính xác nội dung và ý nghĩa của nguyên tác.

**5. ĐỊNH DẠNG KẾT QUẢ:**
- **Chỉ Nội Dung:** Chỉ cung cấp phần văn bản đã dịch hoàn chỉnh. Không thêm bất kỳ lời giải thích, chú thích, bình luận, hay thông tin nào khác.
'''

BOOK_INFO_PROMPT = """
Dịch tiêu đề / tên tác giả sau đoạn từ Tiếng Trung sang Tiếng Việt
Ưu tiên sử dụng từ Hán Việt
Chỉ cung cấp phần văn bản đã dịch hoàn chỉnh. Không thêm bất kỳ lời giải thích, chú thích, bình luận, hay thông tin nào khác.
"""

SENTENCES_PROMPT = """
Bạn sẽ đóng vai một dịch giả chuyên nghiệp. Những câu sau đây được dịch từ Tiếng Trung sang Tiếng Việt tuy nhiên chưa được hoàn chỉnh, còn chứa những từ Tiếng Trung chưa được dịch. 
Hãy giúp tôi dịch lại các câu đó để đảm bảo có một bản dịch bằng Tiếng Việt hoàn chỉnh. Đảm bảo các câu được dịch mượt mà, tự nhiên và dễ hiểu.
Trả về kết quả dưới dạng JSON với key là từ câu ban đầu và value là câu được dịch hoàn chỉnh tương ứng, không chứa bất kỳ từ Tiếng Trung nào còn sót, không thêm bất kỳ lời giải thích, chú thích, bình luận, hay thông tin nào khác.
"""

INCOMPLETE_HANDLE_PROMPT = """
**Yêu cầu:**

Bạn sẽ đóng vai một dịch giả chuyên nghiệp. Nhiệm vụ của bạn là tiếp nhận một đoạn văn bản Tiếng Việt vốn được dịch từ Tiếng Trung nhưng chưa hoàn chỉnh, còn sót lại các từ hoặc ký tự Tiếng Trung.

Bạn cần dịch lại toàn bộ đoạn văn này sang Tiếng Việt một cách hoàn chỉnh và tự nhiên, đảm bảo loại bỏ **tuyệt đối** mọi yếu tố Tiếng Trung (từ ngữ, ký tự).

**Tiêu chí bắt buộc:**

1.  **Yêu cầu đầu ra:** Giữ nguyên những câu đã dịch, chỉ dịch những câu chưa được dịch hoàn chỉnh sử dụng Hán Việt hợp lý sao cho phù hợp với cách dịch ban đầu, câu văn lưu loát, mượt mà, tự nhiên, dễ hiểu. 
2.  **Độ chính xác:** Bản dịch cuối cùng **chỉ được phép chứa Tiếng Việt**. Không được sót lại bất kỳ ký tự, từ ngữ Tiếng Trung nào.
3.  **Chỉ văn bản:** Chỉ cung cấp văn bản đã được dịch hoàn chỉnh. Không thêm bất kỳ lời giải thích, chú thích, bình luận, hay thông tin nào khác.
"""
