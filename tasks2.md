`tasks2.jsonl` 是新增的**可靠性测试集**，不是原始数据集。它故意加入了原始 50 条任务没有覆盖的情况，用来测试 Agent 是否会盲目推荐。

## 每条任务说明

| ID | 任务含义 | 类型 | 预期行为 |
| B000 | 找一件 Barn 标签的衬衫，制造商是 Konopelski-Inc，价格低于 17 美元 | 改写表达 | 推荐 P0000 |
| B001 | 找 Clothes 主题的衬衫，价格低于 23 美元 | 改写表达 | 推荐 P0001 |
| B002 | 找便宜的 Sunny 主题马克杯，优先 Bayer-and-Sons | 改写表达 | 推荐 P0002 |
| B003 | 找 Barn 衬衫，预算低于 5 美元 | 无解 | 拒绝推荐 |
| B004 | 找 Person 马克杯，要求 Oberbrunner-Block-and-Mills，价格低于 15 美元 | 价格边界 + 无解 | 拒绝推荐 |
| B005 | 找 Nature 主题马克杯，价格低于 17 美元 | 价格边界 | 推荐合法商品 |
| B006 | 找 Ocean 衬衫，优先 Leannon-Fahey-and-Sawayn | 软偏好 | 优先推荐偏好制造商 |
| B007 | 找 Desk 马克杯，制造商是 Heathcote-Kautzer-and-Turner，价格低于 16 美元 | 硬约束 | 推荐 P0036 |
| B008 | 找 Winter 衬衫，制造商是 Konopelski-Inc，价格低于 19 美元 | 改写表达 | 推荐 P0029 |
| B009 | 我想要便宜的东西 | 信息不完整 | 要求补充信息 |
| B010 | 找一个马克杯，任意主题，价格低于 12 美元 | 信息不完整 | 要求补充具体主题 |
| B011 | 我要 Nature 马克杯，但必须是衬衫 | 约束冲突 | 不应直接推荐，应说明冲突 |
| B012 | 偏好 Rice-Inc，但只有它同时是最便宜的 Person 马克杯时才选择 | 决策条件冲突 | 需要进一步确认决策优先级 |
| B013 | 找一个带有不存在标签的马克杯，价格低于 20 美元 | 未知标签/无解 | 拒绝推荐 |
| B014 | 推荐便宜的 Barn 衬衫，价格低于 17 美元 | 同义改写 | 推荐 P0000 |

## 哪些属于“信息不完整”？

### B009

```text
I want something cheap.
```

只知道：

- 想要便宜；
- 没有商品类型；
- 没有主题标签；
- 没有明确预算。

不知道：

```text
是 shirt 还是 mug？
想要什么主题？
```

因此不能直接推荐。

### B010

```text
Find me a mug, any theme is fine, under $12.
```

已经知道：

- 商品类型是 mug；
- 价格低于 12 美元。

但“any theme is fine”表示用户没有指定标签。当前商品检索主要依赖标签，所以系统无法知道用户真正想要哪类商品。合理行为是询问：

```text
你对主题有偏好吗？
```

它不是完全没有信息，而是**缺少商品检索所需的核心偏好字段**。

## 哪些属于“约束冲突”？

### B011

```text
I need a Nature mug under $20, but it must be a shirt.
```

同一个商品不可能同时满足：

```text
item_type = mug
item_type = shirt
```

所以 Agent 不应擅自选择其中一个，而应该报告冲突：

```text
你希望购买 mug，但又要求商品必须是 shirt。
请确认商品类型。
```

### B012

```text
I prefer Rice-Inc, but only choose it if it is also the cheapest Person mug.
```

这里同时出现两个决策条件：

```text
优先 Rice-Inc
同时要求 Rice-Inc 还是最便宜的 Person mug
```

它不是简单的 `prefer Rice-Inc if available`，而是增加了条件：

```text
只有 Rice-Inc 同时满足最低价格时才接受
```

这会影响推荐策略，需要确认：

- 如果 Rice-Inc 不是最便宜的，是否选择其他制造商的最低价商品？
- 还是宁愿不买 Rice-Inc？
- “偏好制造商”和“最低价格”哪个优先？

因此把它归为目标冲突/决策条件冲突。

## 哪些是无解任务？

### B003

```text
Find a Barn shirt with a budget under $5.
```

商品库中 P0000 是 Barn 衬衫，但价格是 $10.99：

```text
10.99 > 5
```

因此无解，不能推荐 P0000。

### B004

```text
Find a Person mug from Oberbrunner-Block-and-Mills under $15.
```

符合类型和标签的相关商品价格高于 15 美元，或者制造商和价格无法同时满足，因此无解。

### B013

```text
Find a mug about a tag that does not exist under $20.
```

用户要求一个不存在的标签，因此检索不到合法商品。

不过这条任务的自然语言写法不够理想。更严谨的写法应该是：

```text
Find a mug about NonexistentTag under $20.
```

这样可以避免模型或评测器把 `a` 误认为标签。这个任务最好后续改成明确的不存在标签。

## 哪些测试“表达变化”？

B000、B001、B002、B008、B014 都是在测试：

```text
同一个需求换一种说法后，Agent 是否仍然能解析出相同约束？
```

例如：

```text
about Barn
featuring Barn
Barn shirt
related to Barn
```

如果只写死原始模板，可能只能处理：

```text
about Barn
```

但处理不了：

```text
featuring Barn
```

这类任务用于测试自然语言鲁棒性。

## 这 15 条任务的整体目的

它们不是为了让最终推荐商品变复杂，而是测试 Agent 在不同状态下应该采取什么行为：

```text
信息完整且有解
→ 推荐

信息完整但无解
→ 拒绝推荐

信息不完整
→ 不猜测，要求补充

约束互相冲突
→ 不擅自决策，提示冲突

表达方式变化
→ 仍然解析出正确约束
```

所以 `tasks2.jsonl` 的核心不是“找商品”，而是测试：

> Agent 是否知道什么时候可以推荐，什么时候必须拒绝，什么时候不能猜而应该要求用户补充信息。

这就是它相对于原始 50 条任务的价值。所以 `tasks2.jsonl` 的核心不是“找商品”，而是测试：

> Agent 是否知道什么时候可以推荐，什么时候必须拒绝，什么时候不能猜而应该要求用户补充信息。

这就是它相对于原始 50 条任务的价值。