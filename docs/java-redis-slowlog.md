# Java Redis 慢查询记录

Redis 没有传统关系型数据库里的 `slow query log` 表，但它自带了慢日志能力，可通过 `SLOWLOG` 命令记录执行时间超过阈值的命令。  
在 Java 项目中，通常有两种做法：

1. 使用 Redis 原生慢日志：让 Redis 服务端记录，再由 Java 定期拉取。
2. 在 Java 客户端侧补充埋点：记录请求耗时、命令名、参数摘要和异常信息。

生产环境推荐两者结合使用：  
**服务端 SLOWLOG 用来确认 Redis 真实执行慢；客户端埋点用来补齐网络耗时、线程池排队和业务上下文。**

## 1. Redis 服务端开启慢日志

常见配置：

```conf
# 单位: 微秒。10000 表示 10ms
slowlog-log-slower-than 10000

# 最多保留 1024 条
slowlog-max-len 1024
```

也可以在线修改：

```bash
CONFIG SET slowlog-log-slower-than 10000
CONFIG SET slowlog-max-len 1024
```

常用命令：

```bash
SLOWLOG LEN
SLOWLOG GET 128
SLOWLOG RESET
```

说明：

- `slowlog-log-slower-than` 为单条命令阈值，单位是微秒。
- Redis 记录的是**命令在服务端执行的耗时**，**不包含网络传输时间**。
- `SLOWLOG` 是内存结构，不是持久化审计日志；实例重启后可能丢失。

## 2. Jedis 示例

如果项目使用 Jedis，可以直接调用 `slowlogGet`：

```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.resps.Slowlog;

import java.util.List;

public class JedisSlowlogExample {

    public static void main(String[] args) {
        try (Jedis jedis = new Jedis("127.0.0.1", 6379)) {
            List<Slowlog> entries = jedis.slowlogGet(20);

            for (Slowlog entry : entries) {
                System.out.println("id=" + entry.getId());
                System.out.println("timestamp=" + entry.getTimeStamp());
                System.out.println("durationMicros=" + entry.getExecutionTime());
                System.out.println("command=" + String.join(" ", entry.getArgs()));
                System.out.println("clientName=" + entry.getClientName());
                System.out.println("clientIpPort=" + entry.getClientIpPort());
                System.out.println("---");
            }
        }
    }
}
```

适合做法：

- 定时任务每 30 秒或 1 分钟拉取一次。
- 根据慢日志 `id` 去重，避免重复上报。
- 将结果写入应用日志、ES、ClickHouse 或告警系统。

## 3. Lettuce 示例

如果项目使用 Lettuce，可以执行原生命令读取：

```java
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;

import java.util.List;

public class LettuceSlowlogExample {

    public static void main(String[] args) {
        RedisClient client = RedisClient.create("redis://127.0.0.1:6379");

        try (StatefulRedisConnection<String, String> connection = client.connect()) {
            RedisCommands<String, String> commands = connection.sync();

            List<Object> slowlogs = commands.dispatch(
                io.lettuce.core.protocol.CommandType.SLOWLOG,
                new io.lettuce.core.output.ArrayOutput<>(io.lettuce.core.codec.StringCodec.UTF8),
                new io.lettuce.core.protocol.CommandArgs<>(io.lettuce.core.codec.StringCodec.UTF8)
                    .add("GET")
                    .add(20)
            );

            System.out.println(slowlogs);
        } finally {
            client.shutdown();
        }
    }
}
```

Lettuce 读取慢日志时，很多项目会进一步封装成统一对象，避免直接处理底层数组结构。

## 4. Java 侧做二次记录

只依赖 Redis `SLOWLOG` 还不够，因为它看不到：

- 网络抖动
- 连接池等待
- 客户端序列化耗时
- 业务线程阻塞

因此建议在 Java 客户端侧也记录一次：

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RedisCommandLogger {

    private static final Logger log = LoggerFactory.getLogger(RedisCommandLogger.class);
    private static final long THRESHOLD_MS = 50;

    public <T> T execute(String command, String key, RedisCallback<T> callback) {
        long start = System.nanoTime();
        try {
            return callback.call();
        } finally {
            long costMs = (System.nanoTime() - start) / 1_000_000;
            if (costMs >= THRESHOLD_MS) {
                log.warn("redis slow command, command={}, key={}, costMs={}", command, key, costMs);
            }
        }
    }

    @FunctionalInterface
    public interface RedisCallback<T> {
        T call();
    }
}
```

推荐记录字段：

- `command`：命令名，如 `GET`、`HGETALL`、`ZRANGE`
- `key`：关键 key，必要时做脱敏
- `costMs`：客户端总耗时
- `traceId`：便于关联链路
- `exception`：是否失败
- `node`：Redis 节点地址

## 5. 定时采集 Redis 慢日志的思路

可以在应用中加一个轻量定时任务：

1. 调用 `SLOWLOG GET N`
2. 读取返回的慢日志 ID
3. 与上次处理过的最大 ID 对比
4. 仅上报新增记录
5. 写入日志平台或发送告警

伪代码示例：

```java
long lastProcessedId = -1;

for (Slowlog entry : jedis.slowlogGet(128)) {
    if (entry.getId() <= lastProcessedId) {
        continue;
    }

    // 上报到日志或监控系统
    report(entry);

    lastProcessedId = Math.max(lastProcessedId, entry.getId());
}
```

如果部署多个实例，建议按实例维度分别记录 `lastProcessedId`。

## 6. 生产环境排查建议

出现 Redis 慢查询时，通常优先看这些问题：

1. **大 Key**：例如一次 `HGETALL`、`LRANGE 0 -1` 读取大量数据
2. **复杂命令**：如 `SORT`、大范围 `ZRANGE`、聚合型 Lua 脚本
3. **热 Key**：高并发争抢同一个 Key
4. **阻塞命令**：Lua 执行过长、批量删除、全量扫描
5. **内存压力**：淘汰、碎片整理、持久化导致抖动

建议同时观察：

- Redis `INFO commandstats`
- Redis `INFO stats`
- `LATENCY LATEST`
- 应用侧慢日志
- JVM 线程池与连接池使用情况

## 7. 实际建议

- Redis 服务端开启 `SLOWLOG`，阈值先设为 `5ms ~ 10ms` 再按实际调整
- Java 客户端再加一层慢调用日志，阈值可先设为 `20ms ~ 50ms`
- 参数不要完整打印，避免日志泄露敏感数据或放大日志量
- 对于批量命令，记录参数数量和大小摘要，不要直接打印全部内容
- 慢日志最好接入监控平台，而不是只写本地文件

## 8. 总结

如果你问的是“**Java 怎么记录 Redis 慢查询**”，最稳妥的方案是：

1. **Redis 端开启 `SLOWLOG`**
2. **Java 定时读取 `SLOWLOG GET`**
3. **Java 客户端对 Redis 调用再做耗时埋点**

这样既能看到 Redis 服务端真实执行慢，也能看到调用链整体慢，排查会更完整。
