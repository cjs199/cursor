# Manticore Search 建表时指定中文分词

Manticore Search 对中文（CJK）分词的官方推荐方案是基于 **ICU**（International Components for Unicode）。本文给出建表（`CREATE TABLE`）时指定中文分词的几种常见做法、关键参数说明，以及验证分词效果的方法。

---

## 1. 前置条件

- Manticore Search 版本建议 **≥ 3.1**（更推荐 4.x / 6.x，对 ICU 支持更完善）。
- 服务端需要内置或加载 ICU 库。官方 Docker 镜像 `manticoresearch/manticore` 已经自带 ICU，无需额外安装。
- 如果是自行编译/安装的版本，启动后可通过下面的命令确认 ICU 是否可用：

```sql
SHOW STATUS LIKE 'mysql_version';
SHOW THREADS OPTION format=all;
```

更直接的验证方式见本文「第 4 节：验证分词效果」。

---

## 2. 推荐方案：`morphology = icu_chinese`

这是 Manticore 官方文档为中文（以及与中文混排的英文/数字）推荐的方式。它使用 ICU 自带的中文分词器把连续的汉字切成词。

```sql
CREATE TABLE articles (
    id      BIGINT,
    title   TEXT,
    content TEXT,
    author  STRING,
    created TIMESTAMP
)
charset_table  = 'cjk, non_cjk'
morphology     = 'icu_chinese'
min_word_len   = 1
html_strip     = 1;
```

关键参数说明：

| 参数 | 作用 |
| --- | --- |
| `charset_table = 'cjk, non_cjk'` | 使用内置别名，让 CJK 字符（汉字、日文、韩文）和非 CJK 字符（英文、数字等）都纳入索引字符集。 |
| `morphology = 'icu_chinese'` | 启用 ICU 中文分词器；查询和入库时会自动调用 ICU 把汉字串切成词。 |
| `min_word_len = 1` | 中文一个字也可能成词（例如「猫」「人」），建议设为 1，否则单字会被忽略。 |
| `html_strip = 1` | 如果存的是 HTML/富文本，建议开启，避免标签干扰分词。 |

> 注意：从 Manticore 6.x 开始，`charset_table` 可以直接写 `chinese, non_cjk`，效果与 `cjk, non_cjk` 相同；老版本如果报别名不存在，就用 `cjk, non_cjk`。

---

## 3. 其他可选方案

### 3.1 N-gram 分词（不依赖 ICU）

如果环境里没有 ICU，或者对召回率要求高于精确度，可以使用 **二元/N-gram** 分词，对每个汉字按 N 字一组切分：

```sql
CREATE TABLE articles_ngram (
    id      BIGINT,
    title   TEXT,
    content TEXT
)
charset_table = 'non_cjk'
ngram_len     = 1
ngram_chars   = 'cjk';
```

- `ngram_len = 1` 配合 `ngram_chars = 'cjk'`：每个汉字单独成词。
- 也可以写 `ngram_len = 2` 做 bigram，但通常 `ngram_len = 1` 在 Manticore 中已经能很好地匹配中文短语查询。
- 优点：实现简单，不依赖外部分词库；缺点：索引体积更大，相关性排序不如 ICU 分词。

### 3.2 RT 实时表（与 plain 表写法一致）

Manticore 的 `CREATE TABLE` 默认就是 RT（real-time）表，上面两种写法都直接适用。例如建一个支持实时插入的中文 RT 表：

```sql
CREATE TABLE docs_rt (
    id      BIGINT,
    title   TEXT,
    body    TEXT,
    tags    MULTI
)
charset_table = 'cjk, non_cjk'
morphology    = 'icu_chinese'
min_word_len  = 1
rt_mem_limit  = '256M';
```

### 3.3 通过配置文件（`manticore.conf`）方式

如果走传统的配置文件而不是 SQL，对应写法是：

```ini
table articles {
    type            = rt
    path            = /var/lib/manticore/articles

    rt_field        = title
    rt_field        = content
    rt_attr_uint    = author_id
    rt_attr_timestamp = created

    charset_table   = cjk, non_cjk
    morphology      = icu_chinese
    min_word_len    = 1
    html_strip      = 1
}
```

修改配置后需要 `searchd --stop` 后重启，或者使用 `RELOAD INDEXES`。

---

## 4. 验证分词效果

建好表之后，用 `CALL KEYWORDS` 看实际切词结果：

```sql
CALL KEYWORDS('我爱北京天安门', 'articles');
```

预期返回类似：

```
+------+-----------+------------+
| qpos | tokenized | normalized |
+------+-----------+------------+
| 1    | 我        | 我         |
| 2    | 爱        | 爱         |
| 3    | 北京      | 北京       |
| 4    | 天安门    | 天安门     |
+------+-----------+------------+
```

如果只看到一个个汉字而没有「北京」「天安门」这样的词，通常说明：

1. `morphology` 没设成 `icu_chinese`；或
2. 当前 Manticore 版本没有编译进 ICU；或
3. `charset_table` 没把 CJK 字符纳入。

也可以直接插入数据并搜索：

```sql
INSERT INTO articles (id, title, content) VALUES
  (1, '北京天安门', '我爱北京天安门，天安门上太阳升'),
  (2, '上海外滩',  '上海的外滩夜景非常漂亮');

SELECT id, title FROM articles WHERE MATCH('天安门');
SELECT id, title FROM articles WHERE MATCH('"北京 天安门"/2');
```

---

## 5. 常见坑

1. **忘了设 `min_word_len = 1`**：默认是 1，但有些教程会改成 2，导致单字查不到。
2. **`charset_table` 覆盖了默认值**：`charset_table` 一旦显式指定，就会**完全替换**默认值，所以英文/数字要靠 `non_cjk` 别名带回来；漏掉就会出现「中文能搜，英文搜不到」。
3. **同时用 `morphology = icu_chinese` 和 `ngram_*`**：这两类方案不要混用，否则切词行为难以预测。
4. **混合中英文短语查询**：用 `MATCH('"机器学习 GPU"')` 时，记得 `charset_table` 同时包含 `cjk, non_cjk`，并视情况开启 `blend_chars`（例如希望 `C++`、`.NET` 不被切开时）：

   ```sql
   ALTER TABLE articles SET blend_chars = '+, &, U+23, ., -';
   ```

5. **历史版本兼容**：早期版本曾经用 `chinese_t` / `ngram_chars = U+3000..U+9FFF` 这种写法，新版本统一推荐 `cjk` / `non_cjk` 别名 + `icu_chinese`，可读性和正确性都更好。

---

## 6. 速查模板

最常用的「中文 + 英文混排」建表模板，直接复制改字段即可：

```sql
CREATE TABLE my_table (
    id      BIGINT,
    title   TEXT,
    content TEXT,
    tags    MULTI,
    created TIMESTAMP
)
charset_table = 'cjk, non_cjk'
morphology    = 'icu_chinese'
min_word_len  = 1
html_strip    = 1
index_exact_words = 1;
```

`index_exact_words = 1` 会同时存原词，方便后续做精确匹配（`MATCH('=北京')`）。
