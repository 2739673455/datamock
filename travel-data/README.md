# 旅游平台业务数据
## 业务概述
旅游平台面向用户提供一站式出行产品，覆盖出行前搜索比价、商品详情查看、库存价格确认、下单支付、行程管理和售后退款等完整业务流程。

平台覆盖的出行产品：

- 酒店
- 景点门票
- 机票
- 火车票
- 汽车票
- 接送服务

平台核心业务能力：

- 商品供给：维护酒店房态房价、景点票种库存、交通班次席位和接送服务运力。
- 用户会员：维护用户资料、实名信息、常用出行人、会员等级和积分流水。
- 营销优惠：支持优惠券领取、用户券管理、促销活动和积分抵扣。
- 交易支付：完成订单创建、库存占用、优惠核销、支付发起和订单状态流转。
- 售后退款：支持按订单明细发起退款申请、记录审核结果并跟踪退款打款。

平台用户侧主链路：

- 搜索商品
- 查看详情
- 选择出行人和优惠
- 创建订单
- 发起支付
- 查看订单
- 申请退款

## 快速开始
启动 MySQL 数据库

配置数据库连接参数 [`.env`](./.env)

```bash
uv sync  # 安装依赖

uv run init_db.py  # 初始化数据库
uv run -m generate.main --profile full  # 生成数据

uv run -m app.main  # 启动服务
```

服务启动后访问 FastAPI 文档：

- Swagger UI：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

## 数据定义
### 基础维度
表说明：

- `areas`：地区维表，维护省、市、区县三级行政区域。
- `currencies`：币种维表，维护金额展示与结算使用的币种信息。
- `channels`：渠道维表，维护 App、Web、小程序等来源渠道。
- `transport_hubs`：交通枢纽维表，维护机场、火车站、汽车站等站点信息。
- `suppliers`：供应商主表，维护酒店、景点、交通、接送等供给方主体信息。

依赖关系说明：

- `areas` 通过 `parent_id` 自关联形成省、市、区县三级地区层级。
- `transport_hubs -> areas`：交通枢纽挂接到城市级地区。
- `suppliers -> areas`：供应商挂接到所属地区。

#### `areas`
地区维表，存储省、市、区县三级区域信息。

- `id`：主键 ID。
- `area_code`：地区编码，业务唯一标识。
- `area_name`：地区名称。
- `area_full_name`：地区全称，存储完整行政区名称路径。
- `parent_id`：父级地区 ID，顶级节点为空。
- `level`：地区层级。枚举值：
  - `1`：省级/直辖市级
  - `2`：地市级
  - `3`：区县级
- `postal_code`：邮政编码。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_areas_code (area_code)`
- 外键约束：
  - `fk_areas_parent (parent_id -> areas.id)`
- 业务约束：
  - `level = 1` 时 `parent_id` 为空，`level > 1` 时 `parent_id` 不为空
  - 父节点的 `level = 当前节点 level - 1`

#### `currencies`
币种维表，存储币种代码、名称和符号。

- `id`：主键 ID。
- `currency_code`：币种代码，业务唯一标识。
- `currency_name`：币种名称。
- `symbol`：币种符号。
- `precision_scale`：金额精度位数。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_currencies_code (currency_code)`
- 外键约束：
  - 无
- 业务约束：
  - 无

#### `channels`
渠道维表，定义 App、Web、小程序等下单渠道。

- `id`：主键 ID。
- `channel_code`：渠道编码，业务唯一标识。
- `channel_name`：渠道名称。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_channels_code (channel_code)`
- 外键约束：
  - 无
- 业务约束：
  - 无

#### `transport_hubs`
交通枢纽维表，存储机场、火车站、汽车站等枢纽信息。

- `id`：主键 ID。
- `hub_code`：枢纽编码，业务唯一标识。
- `hub_name`：枢纽名称。
- `hub_type_code`：枢纽类型编码。枚举值：
  - `airport`：机场
  - `railway_station`：火车站
  - `bus_station`：汽车站
- `city_area_id`：所属城市地区 ID，关联 `areas.id`。
- `address`：枢纽地址。
- `latitude`：纬度。
- `longitude`：经度。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_transport_hubs_code (hub_code)`
- 外键约束：
  - `fk_transport_hubs_city (city_area_id -> areas.id)`
- 业务约束：
  - `city_area_id` 须指向 `areas.level = 2` 的城市级区域

#### `suppliers`
供应商主表，存储酒店、景点、交通等供给方主体信息。

- `id`：主键 ID。
- `supplier_code`：供应商编码，业务唯一标识。
- `supplier_name`：供应商名称。
- `supplier_type_code`：供应商类型编码。枚举值：
  - `hotel`：酒店供应商
  - `scenic`：景点供应商
  - `flight`：机票供应商
  - `train`：火车票供应商
  - `bus`：汽车票供应商
  - `transfer`：接送与包车供应商
- `area_id`：所属地区 ID，关联 `areas.id`。
- `contact_name`：联系人姓名。
- `contact_phone`：联系人电话。
- `contact_email`：联系人邮箱。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_suppliers_code (supplier_code)`
- 外键约束：
  - `fk_suppliers_area (area_id -> areas.id)`
- 业务约束：
  - 无

### 用户域
表说明：

- `users`：用户主表，维护账户基础信息和注册地区。
- `user_profiles`：用户实名资料表，维护实名、证件、职业和偏好等扩展信息。
- `travelers`：常用出行人表，维护用户可复用的真实出行人资料。
- `member_accounts`：会员账户表，维护会员等级、积分余额和成长值。
- `member_point_ledger`：积分流水表，维护积分发放、扣减和余额变动记录。

依赖关系说明：

- `users -> user_profiles`：一个用户最多对应一条实名资料。
- `users -> travelers`：一个用户可维护多名常用出行人。
- `users -> member_accounts`：一个用户最多对应一个会员账户。
- `member_accounts -> member_point_ledger`：会员账户下记录多条积分流水。
- `users -> areas`：用户注册地区挂接到城市级地区。

#### `users`
用户主表，存储昵称、手机号、邮箱、注册地区等基础账户信息。

- `id`：主键 ID。
- `nickname`：用户昵称。
- `avatar_url`：头像地址。
- `phone`：手机号，业务唯一标识。
- `email`：邮箱，业务唯一标识。
- `gender_code`：性别编码。枚举值：
  - `male`：男
  - `female`：女
  - `unknown`：未知
- `birth_date`：出生日期。
- `register_area_id`：注册地区 ID，关联 `areas.id`。
- `status_code`：状态编码。枚举值：
  - `normal`：正常
  - `vip`：VIP 用户
  - `inactive`：已停用
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_users_phone (phone)`
  - `uk_users_email (email)`
- 外键约束：
  - `fk_users_area (register_area_id -> areas.id)`
- 业务约束：
  - `register_area_id` 须指向 `areas.level = 2` 的城市级区域
  - `updated_at >= created_at`

#### `user_profiles`
用户实名资料表，与 `users` 一对一，存储真实姓名、证件号、职业、偏好等扩展信息。

- `id`：主键 ID。
- `user_id`：用户 ID，关联 `users.id`。
- `real_name`：真实姓名。
- `identity_no`：证件号码。
- `identity_type_code`：证件类型编码。枚举值：
  - `id_card`：居民身份证
  - `passport`：护照
- `residence_city_name`：居住地全名，固定存储完整行政区名称，如 `上海市 / 浦东新区`、`浙江省 / 杭州市 / 西湖区`。
- `occupation`：职业。
- `preference_payload`：偏好配置，JSON 格式。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_user_profiles_user (user_id)`
- 外键约束：
  - `fk_user_profiles_user (user_id -> users.id)`
- 业务约束：
  - `created_at >= users.created_at`
  - `updated_at >= created_at`

#### `travelers`
常用出行人表，存储乘机人、入住人、游客等真实出行人信息，一个用户可有多名出行人。

- `id`：主键 ID。
- `user_id`：所属用户 ID，关联 `users.id`。
- `traveler_name`：出行人姓名。
- `identity_no`：证件号码。
- `identity_type_code`：证件类型编码。枚举值：
  - `id_card`：居民身份证
  - `passport`：护照
- `gender_code`：性别编码。枚举值：
  - `male`：男
  - `female`：女
- `birth_date`：出生日期。
- `phone`：联系手机号。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_travelers_user_identity (user_id, identity_type_code, identity_no)`
- 外键约束：
  - `fk_travelers_user (user_id -> users.id)`
- 业务约束：
  - `created_at >= users.created_at`
  - `updated_at >= created_at`

#### `member_accounts`
会员账户表，与 `users` 一对一，存储会员等级、积分余额、成长值等信息。

- `id`：主键 ID。
- `user_id`：用户 ID，关联 `users.id`。
- `member_level_code`：会员等级编码。枚举值：
  - `normal`：普通会员（`growth_value < 5000`）
  - `silver`：银卡会员（`growth_value >= 5000 and < 12000`）
  - `gold`：金卡会员（`growth_value >= 12000`）
- `points_balance`：当前积分余额。
- `total_points`：累计获得积分总量。
- `growth_value`：成长值。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_member_accounts_user (user_id)`
- 外键约束：
  - `fk_member_accounts_user (user_id -> users.id)`
- 业务约束：
  - `created_at >= users.created_at`
  - `member_level_code` 由 `growth_value` 决定：`normal -> growth_value < 5000`，`silver -> growth_value >= 5000 and < 12000`，`gold -> growth_value >= 12000`
  - `updated_at >= created_at`

#### `member_point_ledger`
积分流水表，记录积分发放、变更及变更后余额，每次积分变动产生一条记录。

- `id`：主键 ID。
- `user_id`：用户 ID，关联 `users.id`。
- `ledger_type_code`：流水类型编码。枚举值：
  - `signup_bonus`：注册奖励积分
  - `order_earn`：订单消费获积分
  - `order_earn_revoke`：退款撤销订单获积分
  - `point_redeem`：积分抵扣消费
  - `expire`：积分过期清零
  - `admin_adjust`：管理员手动调整
- `points_delta`：积分变动量，正数为增加，负数为扣减。
- `balance_after`：变动后积分余额。
- `created_at`：创建时间。

- 唯一性约束：
  - 无
- 外键约束：
  - `fk_member_point_ledger_user (user_id -> users.id)`
- 业务约束：
  - `created_at >= member_accounts.created_at`
  - `points_delta != 0`
  - 按 `user_id + created_at + id` 排序后，当前 `balance_after = 上一条 balance_after + points_delta`；首条流水由开户初始值推导

### 酒店域
表说明：

- `hotels`：酒店主表，维护酒店基础信息、地区、供应商和设施信息。
- `hotel_room_types`：酒店房型表，维护每家酒店下的可售房型定义。
- `hotel_booking_rules`：酒店预订规则表，维护酒店级预订与入住规则。
- `hotel_room_daily`：酒店房态房价日历表，维护房型按天的库存与价格快照。

依赖关系说明：

- `hotels -> hotel_room_types`：一家酒店可配置多个房型。
- `hotels -> hotel_booking_rules`：一家酒店对应一套酒店级预订规则。
- `hotel_room_types -> hotel_room_daily`：房型按业务日期生成房态房价日历。
- `hotels -> areas`：酒店挂接到城市级地区。
- `hotels -> suppliers`：酒店挂接到酒店供应商。
- `hotel_room_daily -> currencies`：房态房价日历挂接币种。

#### `hotels`
酒店主表，存储酒店基础信息、地址、星级、设施、供应商等信息。

- `id`：主键 ID。
- `hotel_code`：酒店编码，业务唯一标识。
- `hotel_name`：酒店名称。
- `hotel_type_code`：酒店类型编码。枚举值：
  - `luxury`：豪华型
  - `business`：商务型
  - `resort`：度假型
  - `boutique`：精品型
- `star_rating_code`：星级编码。枚举值：
  - `3`：三星
  - `4`：四星
  - `5`：五星
- `area_id`：所属城市地区 ID，关联 `areas.id`。
- `address`：酒店地址。
- `latitude`：纬度。
- `longitude`：经度。
- `summary`：酒店简介。
- `facility_payload`：设施标签，JSON 数组格式，如 `["wifi", "parking", "breakfast", "gym"]`。
- `check_in_time`：最早入住时间，顾客不得早于此时间办理入住。
- `check_out_time`：最晚退房时间，顾客须在此时间前完成退房。
- `contact_phone`：联系电话。
- `supplier_id`：供应商 ID，关联 `suppliers.id`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_hotels_code (hotel_code)`
- 外键约束：
  - `fk_hotels_area (area_id -> areas.id)`
  - `fk_hotels_supplier (supplier_id -> suppliers.id)`
- 业务约束：
  - `area_id` 须指向 `areas.level = 2` 的城市级区域
  - `supplier_id` 须指向 `suppliers.supplier_type_code = 'hotel'` 的供应商
  - `updated_at >= created_at`

#### `hotel_room_types`
酒店房型表，存储房型名称、面积、床型、可住人数等信息，每家酒店可有多个房型。

- `id`：主键 ID。
- `hotel_id`：所属酒店 ID，关联 `hotels.id`。
- `room_type_code`：房型编码，业务唯一标识，格式为 `{hotel_code}_{类别缩写}_{序号}`，如 `HOTEL000001_DBL_01`。类别缩写见 `room_type_category_code` 映射。
- `room_type_name`：房型名称。枚举值（由 `room_type_category_code` 派生）：
  - `大床房`
  - `双床房`
  - `套房`
  - `家庭房`
- `room_type_category_code`：房型分类编码。枚举值：
  - `double`
  - `twin`
  - `suite`
  - `family`
- `area_size`：房间面积（平方米）。
- `max_guests`：最大入住人数。
- `amenity_payload`：房间设施，JSON 数组格式，如 `["window", "desk", "bathroom", "tv"]`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_hotel_room_type_code (room_type_code)`
- 外键约束：
  - `fk_hotel_room_types_hotel (hotel_id -> hotels.id)`
- 业务约束：
  - `created_at >= hotels.created_at`
  - `updated_at >= created_at`

#### `hotel_booking_rules`
酒店预订规则表，与 `hotels` 一对一，存储最晚保留时间、最少连住天数等规则。

- `id`：主键 ID。
- `hotel_id`：所属酒店 ID，关联 `hotels.id`。
- `hold_until_time`：最晚保留房间时间。
- `min_stay_nights`：最少连住天数。
- `max_room_count`：单次最多预订间数。
- `rule_payload`：扩展规则配置，JSON 格式，如 `{"cancel_before_hours": 24, "support_invoice": true}`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_hotel_booking_rules_hotel (hotel_id)`
- 外键约束：
  - `fk_hotel_booking_rules_hotel (hotel_id -> hotels.id)`
- 业务约束：
  - `created_at >= hotels.created_at`
  - `updated_at >= created_at`

#### `hotel_room_daily`
酒店房态房价日历表，存储房型按天的库存与价格。

- `id`：主键 ID。
- `room_type_id`：房型 ID，关联 `hotel_room_types.id`。
- `business_date`：业务日期。
- `total_inventory`：总库存。
- `available_inventory`：可售库存。
- `reserved_inventory`：预占库存。
- `sold_inventory`：已售库存。
- `currency_code`：币种编码，关联 `currencies.currency_code`。
- `sale_price_amount`：销售价。
- `settlement_price_amount`：结算价，用户成交后，平台向供应商支付的费用。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_hotel_room_daily (room_type_id, business_date)`
- 外键约束：
  - `fk_hotel_room_daily_room (room_type_id -> hotel_room_types.id)`
  - `fk_hotel_room_daily_currency (currency_code -> currencies.currency_code)`
- 业务约束：
  - `available_inventory + reserved_inventory + sold_inventory = total_inventory`
  - `settlement_price_amount <= sale_price_amount`
  - `created_at >= hotel_room_types.created_at`
  - `business_date >= DATE(created_at)`
  - `updated_at >= created_at`

### 景点域
表说明：

- `scenic_spots`：景点主表，维护景点基础信息、等级、地区和供应商信息。
- `scenic_ticket_types`：景点票种表，维护成人票、学生票、家庭票等票种定义。
- `scenic_booking_rules`：景点预订规则表，维护景点级预订和退改规则。
- `scenic_ticket_daily`：景点票日历表，维护票种按天的库存与价格快照。

依赖关系说明：

- `scenic_spots -> scenic_ticket_types`：一个景点可配置多个票种。
- `scenic_spots -> scenic_booking_rules`：一个景点对应一套景点级预订规则。
- `scenic_ticket_types -> scenic_ticket_daily`：票种按业务日期生成库存与价格日历。
- `scenic_spots -> areas`：景点挂接到城市级地区。
- `scenic_spots -> suppliers`：景点挂接到景点供应商。
- `scenic_ticket_daily -> currencies`：景点票日历挂接币种。

#### `scenic_spots`
景点主表，存储景点基础资料、等级、地址、标签、供应商等信息。

- `id`：主键 ID。
- `scenic_code`：景点编码，业务唯一标识。
- `scenic_name`：景点名称。
- `scenic_type_code`：景点类型编码。枚举值：
  - `theme_park`：主题公园
  - `museum`：博物馆
  - `mountain`：山地景区
  - `heritage`：文化遗产
  - `wetland`：湿地公园
  - `beach`：海滨景区
  - `snow`：冰雪景区
  - `forest`：森林公园
  - `waterfall`：瀑布溪流
  - `cultural_square`：文化广场
  - `ancient_town`：古镇古街
  - `religious`：宗教场所
  - `theme_water`：水上乐园
  - `zoo`：动物园
  - `botanical_garden`：植物园
  - `industrial_tourism`：工业旅游
  - `red_tourism`：红色旅游
  - `ecological`：生态景区
- `rating_code`：等级编码。枚举值：
  - `5A`
  - `4A`
  - `3A`
- `area_id`：所属城市级地区 ID，关联 `areas.id`。
- `address`：景点地址。
- `latitude`：纬度。
- `longitude`：经度。
- `summary`：景点简介。
- `tag_payload`：标签，JSON 数组格式，如 `["family", "sightseeing", "culture"]`。
- `open_time`：每日开放时间（小时:分钟），如 `08:00`。
- `close_time`：每日关闭时间（小时:分钟），如 `18:00`。
- `supplier_id`：供应商 ID，关联 `suppliers.id`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_scenic_spots_code (scenic_code)`
- 外键约束：
  - `fk_scenic_spots_area (area_id -> areas.id)`
  - `fk_scenic_spots_supplier (supplier_id -> suppliers.id)`
- 业务约束：
  - `area_id` 须指向 `areas.level = 2` 的城市级区域
  - `supplier_id` 须指向 `suppliers.supplier_type_code = 'scenic'` 的供应商
  - `updated_at >= created_at`

#### `scenic_ticket_types`
景点票种表，存储成人票、学生票、家庭票等票种定义。

- `id`：主键 ID。
- `scenic_spot_id`：所属景点 ID，关联 `scenic_spots.id`。
- `ticket_type_code`：票种编码，业务唯一标识，格式为 `{scenic_code}_{类别缩写}_{序号}`，如 `SCENIC000001_ADULT_01`。
- `ticket_type_name`：票种名称。枚举值（由 `ticket_category_code` 派生）：
  - `成人票`
  - `学生票`
  - `家庭票`
  - `夜场票`
- `ticket_category_code`：票种分类编码。枚举值：
  - `adult`
  - `student`
  - `family`
  - `night`
- `benefit_payload`：权益描述，JSON 格式，如 `{"enter_times": 1, "refund_rule": "T-1 free"}`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_scenic_ticket_type_code (ticket_type_code)`
- 外键约束：
  - `fk_scenic_ticket_types_spot (scenic_spot_id -> scenic_spots.id)`
- 业务约束：
  - `created_at >= scenic_spots.created_at`
  - `updated_at >= created_at`

#### `scenic_booking_rules`
景点预订规则表，与 `scenic_spots` 一对一，存储最晚预订时间、退票规则等配置。

- `id`：主键 ID。
- `scenic_spot_id`：所属景点 ID，关联 `scenic_spots.id`。
- `latest_booking_time`：最晚预订时间。
- `rule_payload`：扩展规则配置，JSON 格式，如 `{"支持退票": true, "refund_rule": "T-1 free"}`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_scenic_booking_rules_spot (scenic_spot_id)`
- 外键约束：
  - `fk_scenic_booking_rules_spot (scenic_spot_id -> scenic_spots.id)`
- 业务约束：
  - `created_at >= scenic_spots.created_at`
  - `updated_at >= created_at`

#### `scenic_ticket_daily`
景点票日历表，存储票种按天的库存与价格。

- `id`：主键 ID。
- `ticket_type_id`：票种 ID，关联 `scenic_ticket_types.id`。
- `business_date`：业务日期。
- `total_inventory`：总库存。
- `available_inventory`：可售库存。
- `reserved_inventory`：预占库存。
- `sold_inventory`：已售库存。
- `currency_code`：币种编码，关联 `currencies.currency_code`。
- `sale_price_amount`：销售价。
- `settlement_price_amount`：结算价，用户成交后，平台向供应商支付的费用。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_scenic_ticket_daily (ticket_type_id, business_date)`
- 外键约束：
  - `fk_scenic_ticket_daily_ticket (ticket_type_id -> scenic_ticket_types.id)`
  - `fk_scenic_ticket_daily_currency (currency_code -> currencies.currency_code)`
- 业务约束：
  - `available_inventory + reserved_inventory + sold_inventory = total_inventory`
  - `settlement_price_amount <= sale_price_amount`
  - `created_at >= scenic_ticket_types.created_at`
  - `business_date >= DATE(created_at)`
  - `updated_at >= created_at`

### 交通域
表说明：

- `flight_routes`、`train_routes`、`bus_routes`：交通线路主表，分别维护航线、火车线路和汽车班线基础信息。
- `flight_departures`、`train_departures`、`bus_departures`：交通班次实例表，维护具体发车日期与时刻。
- `flight_cabin_inventory`、`train_seat_inventory`、`bus_seat_inventory`：交通库存表，维护班次下不同舱位或席别的库存与价格。
- `transfer_services`：接送服务主表，维护接机、送机、包车等服务定义。
- `transfer_service_area_rules`：接送服务区域规则表，维护上下车区域组合的定价规则。
- `transfer_capacity_calendar`：接送运力日历表，维护接送服务按天的容量与售卖快照。

依赖关系说明：

- `flight_routes -> flight_departures -> flight_cabin_inventory`：机票按航线、航班实例、舱位库存三级展开。
- `train_routes -> train_departures -> train_seat_inventory`：火车票按线路、班次实例、席位库存三级展开。
- `bus_routes -> bus_departures -> bus_seat_inventory`：汽车票按班线、班次实例、席位库存三级展开。
- `flight_routes`、`train_routes`、`bus_routes` 均依赖 `transport_hubs`、`areas`、`suppliers`，用于维护出发到达站点、城市和供应商关系。
- `transfer_services -> transfer_service_area_rules`：接送服务维护上下车区域组合规则。
- `transfer_services -> transfer_capacity_calendar`：接送服务按业务日期维护运力日历。
- 交通库存表和价格表统一依赖 `currencies` 维护金额币种。

#### `flight_routes`
航线主表，存储航班号、出发到达枢纽、航司、供应商等信息。

- `id`：主键 ID。
- `route_code`：航线编码，业务唯一标识。
- `flight_no`：航班号。
- `airline_code`：航司编码。枚举值：
  - `MU`：东方航空
  - `CA`：中国国航
  - `CZ`：南方航空
  - `HU`：海南航空
  - `HO`：吉祥航空
  - `3U`：四川航空
  - `FM`：上海航空
  - `9C`：春秋航空
  - `BK`：奥凯航空
  - `KN`：中国联航
  - `SC`：山东航空
  - `TV`：西藏航空
  - `EU`：成都航空
  - `G5`：华夏航空
  - `JR`：天津航空
  - `NS`：河北航空
  - `JD`：首都航空
  - `ZH`：深圳航空
  - `PN`：西部航空
  - `CO`：长龙航空
- `supplier_id`：供应商 ID，关联 `suppliers.id`。
- `departure_hub_id`：出发枢纽 ID，关联 `transport_hubs.id`。
- `arrival_hub_id`：到达枢纽 ID，关联 `transport_hubs.id`。
- `departure_area_id`：出发城市地区 ID，关联 `areas.id`。
- `arrival_area_id`：到达城市地区 ID，关联 `areas.id`。
- `duration_minutes`：飞行时长（分钟）。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_flight_routes_code (route_code)`
- 外键约束：
  - `fk_flight_routes_supplier (supplier_id -> suppliers.id)`
  - `fk_flight_routes_departure_hub (departure_hub_id -> transport_hubs.id)`
  - `fk_flight_routes_arrival_hub (arrival_hub_id -> transport_hubs.id)`
  - `fk_flight_routes_departure_area (departure_area_id -> areas.id)`
  - `fk_flight_routes_arrival_area (arrival_area_id -> areas.id)`
- 业务约束：
  - `departure_area_id` 须指向 `areas.level = 2` 的城市区域
  - `arrival_area_id` 须指向 `areas.level = 2` 的城市区域
  - `departure_hub_id` 须指向 `transport_hubs.hub_type_code = 'airport'` 的枢纽
  - `arrival_hub_id` 须指向 `transport_hubs.hub_type_code = 'airport'` 的枢纽
  - `departure_hub_id` 须指向与 `departure_area_id` 对应的枢纽（即 transport_hubs.city_area_id = departure_area_id）
  - `arrival_hub_id` 须指向与 `arrival_area_id` 对应的枢纽（即 transport_hubs.city_area_id = arrival_area_id）
  - `supplier_id` 须指向 `suppliers.supplier_type_code = 'flight'` 的供应商
  - `updated_at >= created_at`

#### `flight_departures`
航班实例表，存储具体航班日期、起飞时间、到达时间等信息。

- `id`：主键 ID。
- `flight_route_id`：航线 ID，关联 `flight_routes.id`。
- `departure_instance_code`：航班实例编码，业务唯一标识。
- `departure_time`：出发时间。
- `arrival_time`：到达时间。
- `rule_payload`：扩展规则，JSON 格式，存储航班实例级别的规则，如免费托运行李额、手提行李规定、餐食等。示例：
  - `{"free_checked_baggage": {"weight": 23, "piece": 1}, "free_cabin_baggage": {"weight": 5, "size": "40x30x20"}, "meal": true}`
- `status_code`：状态编码。枚举值：
  - `scheduled`：已排班
  - `cancelled`：已取消
  - `done`：已完成
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_flight_departures_code (departure_instance_code)`
- 外键约束：
  - `fk_flight_departures_route (flight_route_id -> flight_routes.id)`
- 业务约束：
  - `arrival_time > departure_time`
  - `departure_time > created_at`
  - `created_at >= flight_routes.created_at`
  - `updated_at >= created_at`

#### `flight_cabin_inventory`
航班舱位库存表，存储具体航班实例下各舱位的库存和价格。

- `id`：主键 ID。
- `flight_departure_id`：航班实例 ID，关联 `flight_departures.id`。
- `cabin_class_code`：舱位等级编码。枚举值：
  - `economy`：经济舱
  - `business`：商务舱
- `currency_code`：币种编码，关联 `currencies.currency_code`。
- `sale_price_amount`：销售价。
- `settlement_price_amount`：结算价，用户成交后，平台向供应商支付的费用。
- `total_inventory`：总库存。
- `available_inventory`：可售库存。
- `reserved_inventory`：预占库存。
- `sold_inventory`：已售库存。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_flight_cabin_inventory (flight_departure_id, cabin_class_code)`
- 外键约束：
  - `fk_flight_cabin_inventory_departure (flight_departure_id -> flight_departures.id)`
- 业务约束：
  - `available_inventory + reserved_inventory + sold_inventory = total_inventory`
  - `settlement_price_amount <= sale_price_amount`
  - `created_at <= flight_departures.departure_time`
  - `updated_at >= created_at`

#### `train_routes`
火车线路主表，存储车次号、出发到达站点、区域、供应商等信息。

- `id`：主键 ID。
- `route_code`：线路编码，业务唯一标识。
- `train_no`：车次号。
- `supplier_id`：供应商 ID，关联 `suppliers.id`。
- `departure_hub_id`：出发站点 ID，关联 `transport_hubs.id`。
- `arrival_hub_id`：到达站点 ID，关联 `transport_hubs.id`。
- `departure_area_id`：出发城市地区 ID，关联 `areas.id`。
- `arrival_area_id`：到达城市地区 ID，关联 `areas.id`。
- `duration_minutes`：运行时长（分钟）。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_train_routes_code (route_code)`
- 外键约束：
  - `fk_train_routes_supplier (supplier_id -> suppliers.id)`
  - `fk_train_routes_departure_hub (departure_hub_id -> transport_hubs.id)`
  - `fk_train_routes_arrival_hub (arrival_hub_id -> transport_hubs.id)`
  - `fk_train_routes_departure_area (departure_area_id -> areas.id)`
  - `fk_train_routes_arrival_area (arrival_area_id -> areas.id)`
- 业务约束：
  - `departure_area_id` 须指向 `areas.level = 2` 的城市区域
  - `arrival_area_id` 须指向 `areas.level = 2` 的城市区域
  - `departure_hub_id` 须指向 `transport_hubs.hub_type_code = 'railway_station'` 的枢纽
  - `arrival_hub_id` 须指向 `transport_hubs.hub_type_code = 'railway_station'` 的枢纽
  - `departure_hub_id` 须指向与 `departure_area_id` 对应的枢纽
  - `arrival_hub_id` 须指向与 `arrival_area_id` 对应的枢纽
  - `supplier_id` 须指向 `suppliers.supplier_type_code = 'train'` 的供应商
  - `updated_at >= created_at`

#### `train_departures`
火车班次实例表，存储具体开车时间、到达时间等信息。

- `id`：主键 ID。
- `train_route_id`：线路 ID，关联 `train_routes.id`。
- `departure_instance_code`：班次实例编码，业务唯一标识。
- `departure_time`：出发时间。
- `arrival_time`：到达时间。
- `status_code`：状态编码。枚举值：
  - `scheduled`：已排班
  - `cancelled`：已取消
  - `done`：已完成
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_train_departures_code (departure_instance_code)`
- 外键约束：
  - `fk_train_departures_route (train_route_id -> train_routes.id)`
- 业务约束：
  - `arrival_time > departure_time`
  - `departure_time > created_at`
  - `created_at >= train_routes.created_at`
  - `updated_at >= created_at`

#### `train_seat_inventory`
火车席位库存表，存储具体班次下不同席别的库存和价格。

- `id`：主键 ID。
- `train_departure_id`：班次实例 ID，关联 `train_departures.id`。
- `seat_class_code`：席位等级编码。枚举值：
  - `second_class`：二等座
  - `first_class`：一等座
  - `business`：商务座
- `currency_code`：币种编码，关联 `currencies.currency_code`。
- `sale_price_amount`：销售价。
- `settlement_price_amount`：结算价，用户成交后，平台向供应商支付的费用。
- `total_inventory`：总库存。
- `available_inventory`：可售库存。
- `reserved_inventory`：预占库存。
- `sold_inventory`：已售库存。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_train_seat_inventory (train_departure_id, seat_class_code)`
- 外键约束：
  - `fk_train_seat_inventory_departure (train_departure_id -> train_departures.id)`
- 业务约束：
  - `available_inventory + reserved_inventory + sold_inventory = total_inventory`
  - `settlement_price_amount <= sale_price_amount`
  - `created_at <= train_departures.departure_time`
  - `updated_at >= created_at`

#### `bus_routes`
汽车班线主表，存储班线名称、出发到达站点、区域、供应商等信息。

- `id`：主键 ID。
- `route_code`：班线编码，业务唯一标识。
- `route_name`：班线名称。
- `supplier_id`：供应商 ID，关联 `suppliers.id`。
- `departure_hub_id`：出发站点 ID，关联 `transport_hubs.id`。
- `arrival_hub_id`：到达站点 ID，关联 `transport_hubs.id`。
- `departure_area_id`：出发城市地区 ID，关联 `areas.id`。
- `arrival_area_id`：到达城市地区 ID，关联 `areas.id`。
- `duration_minutes`：运行时长（分钟）。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_bus_routes_code (route_code)`
- 外键约束：
  - `fk_bus_routes_supplier (supplier_id -> suppliers.id)`
  - `fk_bus_routes_departure_hub (departure_hub_id -> transport_hubs.id)`
  - `fk_bus_routes_arrival_hub (arrival_hub_id -> transport_hubs.id)`
  - `fk_bus_routes_departure_area (departure_area_id -> areas.id)`
  - `fk_bus_routes_arrival_area (arrival_area_id -> areas.id)`
- 业务约束：
  - `departure_area_id` 须指向 `areas.level = 2` 的城市区域
  - `arrival_area_id` 须指向 `areas.level = 2` 的城市区域
  - `departure_hub_id` 须指向 `transport_hubs.hub_type_code = 'bus_station'` 的枢纽
  - `arrival_hub_id` 须指向 `transport_hubs.hub_type_code = 'bus_station'` 的枢纽
  - `departure_hub_id` 须指向与 `departure_area_id` 对应的枢纽
  - `arrival_hub_id` 须指向与 `arrival_area_id` 对应的枢纽
  - `supplier_id` 须指向 `suppliers.supplier_type_code = 'bus'` 的供应商
  - `updated_at >= created_at`

#### `bus_departures`
汽车班次实例表，存储具体发车时间、到达时间等信息。

- `id`：主键 ID。
- `bus_route_id`：班线 ID，关联 `bus_routes.id`。
- `departure_instance_code`：班次实例编码，业务唯一标识。
- `departure_time`：出发时间。
- `arrival_time`：到达时间。
- `status_code`：状态编码。枚举值：
  - `scheduled`：已排班
  - `cancelled`：已取消
  - `done`：已完成
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_bus_departures_code (departure_instance_code)`
- 外键约束：
  - `fk_bus_departures_route (bus_route_id -> bus_routes.id)`
- 业务约束：
  - `arrival_time > departure_time`
  - `departure_time > created_at`
  - `created_at >= bus_routes.created_at`
  - `updated_at >= created_at`

#### `bus_seat_inventory`
汽车席位库存表，存储具体班次下席位库存和价格。

- `id`：主键 ID。
- `bus_departure_id`：班次实例 ID，关联 `bus_departures.id`。
- `seat_class_code`：席位等级编码。枚举值：
  - `coach`：大巴
- `currency_code`：币种编码，关联 `currencies.currency_code`。
- `sale_price_amount`：销售价。
- `settlement_price_amount`：结算价，用户成交后，平台向供应商支付的费用。
- `total_inventory`：总库存。
- `available_inventory`：可售库存。
- `reserved_inventory`：预占库存。
- `sold_inventory`：已售库存。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_bus_seat_inventory (bus_departure_id, seat_class_code)`
- 外键约束：
  - `fk_bus_seat_inventory_departure (bus_departure_id -> bus_departures.id)`
- 业务约束：
  - `available_inventory + reserved_inventory + sold_inventory = total_inventory`
  - `settlement_price_amount <= sale_price_amount`
  - `created_at <= bus_departures.departure_time`
  - `updated_at >= created_at`

#### `transfer_services`
接送服务主表，存储接机、送机、包车等服务定义及基础信息。

- `id`：主键 ID。
- `service_code`：服务编码，业务唯一标识。
- `service_name`：服务名称。
- `service_type_code`：服务类型编码。枚举值：
  - `airport_pickup`：机场接机
  - `airport_dropoff`：机场送机
  - `charter_daily`：包车一日游
  - `station_transfer`：车站接送
- `area_id`：服务地区 ID，关联 `areas.id`（城市级别）。
- `vehicle_type_code`：车型编码。枚举值：
  - `economy`：经济型
  - `comfort`：舒适型
  - `business`：商务型
  - `van`：商务车
- `passenger_capacity`：最大载客人数。
- `supplier_id`：供应商 ID，关联 `suppliers.id`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_transfer_services_code (service_code)`
- 外键约束：
  - `fk_transfer_services_area (area_id -> areas.id)`
  - `fk_transfer_services_supplier (supplier_id -> suppliers.id)`
- 业务约束：
  - `area_id` 须指向 `areas.level = 2` 的城市级区域
  - `supplier_id` 须指向 `suppliers.supplier_type_code = 'transfer'` 的供应商
  - `updated_at >= created_at`

#### `transfer_service_area_rules`
接送服务区域规则表，存储接送区域、承定价及最低价等规则。

- `id`：主键 ID。
- `transfer_service_id`：接送服务 ID，关联 `transfer_services.id`。
- `pickup_area_id`：上车地区 ID，关联 `areas.id`。
- `dropoff_area_id`：下车地区 ID，关联 `areas.id`。
- `price_amount`：承定价，该上下车组合的结算价格。
- `min_price_amount`：最低价，平台保底价。
- `rule_payload`：扩展规则，JSON 对象或数组，存储服务区域级别的附加规则。示例：
  - `[{"type": "night_fee", "amount": 10, "condition": "22:00-06:00"}, {"type": "holiday_fee", "amount": 20, "condition": "weekend"}]`
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_transfer_service_area_rules (transfer_service_id, pickup_area_id, dropoff_area_id)`
- 外键约束：
  - `fk_transfer_service_area_rules_service (transfer_service_id -> transfer_services.id)`
  - `fk_transfer_service_area_rules_pickup (pickup_area_id -> areas.id)`
  - `fk_transfer_service_area_rules_dropoff (dropoff_area_id -> areas.id)`
- 业务约束：
  - `price_amount >= min_price_amount >= 0`
  - `pickup_area_id` 须指向 `areas.level = 2` 的城市级区域
  - `dropoff_area_id` 须指向 `areas.level = 2` 的城市级区域
  - `created_at >= transfer_services.created_at`
  - `updated_at >= created_at`

#### `transfer_capacity_calendar`
接送运力日历表，存储服务按天的容量与售卖情况。

- `id`：主键 ID。
- `transfer_service_id`：接送服务 ID，关联 `transfer_services.id`。
- `business_date`：业务日期。
- `total_inventory`：总库存。
- `available_inventory`：可售库存。
- `reserved_inventory`：预占库存。
- `sold_inventory`：已售库存。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_transfer_capacity_calendar (transfer_service_id, business_date)`
- 外键约束：
  - `fk_transfer_capacity_service (transfer_service_id -> transfer_services.id)`
- 业务约束：
  - `available_inventory + reserved_inventory + sold_inventory = total_inventory`
  - `created_at >= transfer_services.created_at`
  - `business_date >= DATE(created_at)`
  - `updated_at >= created_at`

### 营销域
表说明：

- `coupon_templates`：优惠券模板表，维护券类型、适用范围、有效期和发放规则。
- `user_coupons`：用户优惠券表，维护用户实际持有的券实例。
- `promotions`：促销活动表，维护活动主信息与生效时间。
- `promotion_rules`：促销规则表，维护促销触发条件和优惠内容。
- `promotion_bindings`：促销绑定表，维护活动与具体商品之间的绑定关系。

依赖关系说明：

- `coupon_templates -> user_coupons`：券模板实例化为用户可持有的优惠券。
- `coupon_templates -> suppliers`：券模板可按供应商范围生效。
- `coupon_templates`、`user_coupons` -> `currencies`：优惠券金额字段统一挂接币种。
- `promotions -> promotion_rules`：一个促销活动可配置多条规则。
- `promotions -> promotion_bindings`：一个促销活动可绑定多个具体商品。
- `promotion_bindings` 通过 `product_type_code + target_id` 关联酒店房型、景点票种、交通库存或接送服务等商品对象。

#### `coupon_templates`
优惠券模板表，定义优惠券的发放规则和使用条件。

- `id`：主键 ID。
- `template_code`：模板编码，业务唯一标识。
- `template_name`：模板名称。
- `coupon_type_code`：券类型编码。枚举值：
  - `HOTEL_ROOM_CASH`：酒店满减券
  - `HOTEL_ROOM_DISCOUNT`：酒店折扣券
  - `SCENIC_TICKET_CASH`：景点满减券
  - `SCENIC_TICKET_DISCOUNT`：景点折扣券
  - `FLIGHT_CABIN_CASH`：机票满减券
  - `FLIGHT_CABIN_DISCOUNT`：机票折扣券
  - `TRAIN_SEAT_CASH`：火车票满减券
  - `TRAIN_SEAT_DISCOUNT`：火车票折扣券
  - `BUS_SEAT_CASH`：汽车票满减券
  - `BUS_SEAT_DISCOUNT`：汽车票折扣券
  - `TRANSFER_SERVICE_CASH`：接送服务满减券
  - `TRANSFER_SERVICE_DISCOUNT`：接送服务折扣券
- `applicable_product_type`：适用商品类型，如 `hotel_room`、`scenic_ticket`、`flight_cabin`、`train_seat`、`bus_seat`、`transfer_service`。
- `applicable_supplier_id`：适用供应商 ID，关联 `suppliers.id`，可为空表示不限供应商。
- `currency_code`：货币编码，关联 `currencies.currency_code`。
- `min_spend_amount`：最低消费金额，使用该券的订单最低消费门槛。
- `discount_amount`：优惠值。当券类型为现金券时表示固定减免金额；当券类型为折扣券时表示折扣值/折扣率。
- `max_discount_amount`：最高优惠金额，仅折扣类券适用，表示折扣优惠上限。
- `valid_from`：有效期开始时间。
- `valid_until`：有效期结束时间。
- `total_quantity`：发放总量。
- `per_user_limit`：每人限领数量。
- `rule_payload`：扩展规则，JSON 格式，如 `{"stackable": false}`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_coupon_templates_code (template_code)`
- 外键约束：
  - `fk_coupon_templates_supplier (applicable_supplier_id -> suppliers.id)`
  - `fk_coupon_templates_currency (currency_code -> currencies.currency_code)`
- 业务约束：
  - 当券类型为现金券时：`discount_amount > 0`，`max_discount_amount` 为空
  - 当券类型为折扣券时：`discount_amount` 表示折扣值或折扣率，`max_discount_amount >= 0`
  - `valid_from <= valid_until`
  - 当 `applicable_supplier_id` 不为空时，`applicable_product_type` 必须与 `suppliers.supplier_type_code` 对应匹配：
    `hotel_room -> hotel`、`scenic_ticket -> scenic`、`flight_cabin -> flight`、`train_seat -> train`、`bus_seat -> bus`、`transfer_service -> transfer`
  - `created_at <= valid_from`
  - `updated_at >= created_at`

#### `user_coupons`
用户优惠券表，记录用户实际持有和使用的优惠券实例。

- `id`：主键 ID。
- `template_id`：模板 ID，关联 `coupon_templates.id`。
- `user_id`：用户 ID，关联 `users.id`。
- `coupon_code`：券码，业务唯一标识。
- `currency_code`：货币编码，关联 `currencies.currency_code`，继承自模板。
- `min_spend_amount`：最低消费金额，继承自模板。
- `discount_amount`：优惠值，继承自模板。当券类型为现金券时表示固定减免金额；当券类型为折扣券时表示折扣值/折扣率。
- `max_discount_amount`：最高优惠金额，继承自模板，仅折扣类券适用。
- `valid_from`：有效期开始时间，继承自模板。
- `valid_until`：有效期结束时间，继承自模板。
- `status_code`：状态编码。枚举值：
  - `available`：可用
  - `used`：已使用
  - `expired`：已过期
- `used_at`：使用时间，使用后记录。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_user_coupons_code (coupon_code)`
- 外键约束：
  - `fk_user_coupons_template (template_id -> coupon_templates.id)`
  - `fk_user_coupons_user (user_id -> users.id)`
  - `fk_user_coupons_currency (currency_code -> currencies.currency_code)`
- 业务约束：
  - `valid_from <= valid_until`
  - 当券类型为现金券时：`discount_amount > 0`，`max_discount_amount` 为空
  - 当券类型为折扣券时：`discount_amount` 表示折扣值或折扣率，`max_discount_amount >= 0`
  - `used_at >= created_at`
  - `updated_at >= created_at`

#### `promotions`
促销活动表，存储促销活动主数据。

- `id`：主键 ID。
- `promotion_code`：活动编码，业务唯一标识。
- `promotion_name`：活动名称。
- `promotion_type_code`：活动类型编码。枚举值：
  - `direct_discount`：直接折扣
  - `min_spend_discount`：满减
  - `flashsale`：秒杀
  - `bundling`：套餐
- `currency_code`：货币编码，关联 `currencies.currency_code`。
- `start_time`：活动开始时间。
- `end_time`：活动结束时间。
- `config_payload`：扩展配置，JSON 格式，如 `{"product_type": "hotel_room"}`。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
  - `paused`：暂停
  - `finished`：已结束
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_promotions_code (promotion_code)`
- 外键约束：
  - `fk_promotions_currency (currency_code -> currencies.currency_code)`
- 业务约束：
  - `start_time <= end_time`
  - `created_at <= start_time`
  - `updated_at >= created_at`

#### `promotion_rules`
促销规则表，存储促销活动的具体规则（触发条件 + 优惠内容）。

- `id`：主键 ID。
- `promotion_id`：促销活动 ID，关联 `promotions.id`。
- `rule_name`：规则名称。
- `trigger_type_code`：触发类型编码。枚举值：
  - `min_spend`：满额触发
  - `first_order`：首单触发
  - `time_window`：时段触发
  - `product_count`：数量触发
- `trigger_payload`：触发条件，JSON 格式，如 `{"min_spend": 200}`。
- `benefit_type_code`：优惠类型编码。枚举值：
  - `discount_amount`：固定优惠金额
  - `discount_rate`：折扣率
  - `gift_item`：赠品
- `benefit_payload`：优惠内容，JSON 格式，如 `{"discount_amount": 20}`。
- `sort_order`：排序顺序。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - 无
- 外键约束：
  - `fk_promotion_rules_promotion (promotion_id -> promotions.id)`
- 业务约束：
  - `updated_at >= created_at`

#### `promotion_bindings`
促销绑定表，将促销活动绑定到具体的商品或服务。

- `id`：主键 ID。
- `promotion_id`：促销活动 ID，关联 `promotions.id`。
- `product_type_code`：商品类型编码。枚举值：
  - `hotel_room`：酒店房型
  - `scenic_ticket`：景点票种
  - `flight_cabin`：航班舱位
  - `train_seat`：火车席位
  - `bus_seat`：汽车席位
  - `transfer_service`：接送服务
- `target_id`：目标商品 ID，根据 `product_type_code` 关联不同表。
- `status_code`：状态编码。枚举值：
  - `active`：有效
  - `inactive`：无效
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_promotion_bindings (promotion_id, product_type_code, target_id)`
- 外键约束：
  - `fk_promotion_bindings_promotion (promotion_id -> promotions.id)`
- 业务约束：
  - `product_type_code` 与 `target_id` 必须匹配对应商品表：
    `hotel_room -> hotel_room_types.id`、`scenic_ticket -> scenic_ticket_types.id`、`flight_cabin -> flight_cabin_inventory.id`、`train_seat -> train_seat_inventory.id`、`bus_seat -> bus_seat_inventory.id`、`transfer_service -> transfer_services.id`
  - `updated_at >= created_at`

### 交易与资金域
表说明：

- `orders`：订单主表，维护订单汇总金额、状态、渠道和终态时间。
- `order_items`：订单明细表，维护具体商品明细、履约对象、出行时间和退款状态。
- `order_coupon_usages`：订单用券明细表，维护订单使用的优惠券记录。
- `order_promotion_details`：订单促销明细表，维护订单命中的促销活动和优惠拆分。
- `order_point_usages`：订单积分使用表，维护积分抵扣记录。
- `payments`：支付记录表，维护订单支付单、支付状态和支付方式。
- `refund_requests`：退款申请表，维护按订单明细发起的退款申请。
- `refund_records`：退款记录表，维护退款申请审核通过后的实际打款记录。

依赖关系说明：

- `orders -> order_items`：一个订单可拆分为多条商品明细。
- `orders -> order_coupon_usages`：订单可使用一张或多张优惠券。
- `orders -> order_promotion_details`：订单可命中多条促销优惠明细。
- `orders -> order_point_usages`：订单可记录积分抵扣使用情况。
- `orders -> payments`：订单可产生一条或多条支付记录。
- `order_items -> refund_requests -> refund_records`：退款链路按订单明细发起，并记录实际退款结果。
- `orders -> users`、`orders -> channels`、`orders -> currencies`：订单挂接用户、来源渠道和币种。
- `order_coupon_usages` 依赖 `user_coupons`，`order_promotion_details` 依赖 `promotions`，`order_point_usages` 依赖 `member_point_ledger` 的积分账户口径。

#### `orders`
订单主表，存储订单类型、订单汇总标记、金额拆分、支付时间、终态时间等核心交易信息。

- `id`：主键 ID。
- `order_no`：订单号，业务唯一标识。
- `user_id`：下单用户 ID，关联 `users.id`。
- `order_type_code`：订单类型编码。枚举值：
  - `hotel_room`：酒店订单
  - `scenic_ticket`：景点门票订单
  - `flight_cabin`：机票订单
  - `train_seat`：火车票订单
  - `bus_seat`：汽车票订单
  - `transfer_service`：接送服务订单
- `status_code`：订单状态编码。枚举值：
  - `pending_payment`：待支付
  - `cancelled`：已取消，终态
  - `paid`：已支付
  - `in_progress`：进行中
  - `finished`：已结束，终态
- `currency_code`：货币编码，关联 `currencies.currency_code`。
- `goods_amount`：商品总金额。
- `marketing_discount_amount`：营销优惠金额。
- `coupon_discount_amount`：优惠券优惠金额。
- `point_discount_amount`：积分抵扣金额。
- `payable_amount`：应付金额。
- `paid_amount`：实付金额，无支付时为空。
- `refunded_amount`：退款金额，无退款时为空。
- `settlement_amount`：结算金额，指平台与供应商结算时使用的金额，仅当订单状态为 `finished` 时才有值，否则为空。
- `source_channel_code`：订单来源渠道编码，关联 `channels.channel_code`。
- `cancel_reason`：取消原因说明文本。
- `paid_at`：支付完成时间。
- `finalized_at`：订单终结时间。订单进入终态时必须有值，包括 `cancelled` 和 `finished`；取消订单取取消时间，已结束订单取订单下明细完结时间中的最晚时间，明细完结时间指 `order_items.completed_at` 或 `order_items.refunded_at`。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_orders_no (order_no)`
- 外键约束：
  - `fk_orders_user (user_id -> users.id)`
  - `fk_orders_channel (source_channel_code -> channels.channel_code)`
- 业务约束：
  - `goods_amount - marketing_discount_amount - coupon_discount_amount - point_discount_amount = payable_amount`
  - `marketing_discount_amount + coupon_discount_amount + point_discount_amount <= goods_amount`
  - 当订单状态为 `pending_payment` 时：
    - `cancel_reason` 为空
    - `paid_amount`、`paid_at`、`refunded_amount`、`settlement_amount`、`finalized_at` 为空
    - 所有 `order_items.status_code = 'pending_payment'`
  - 当订单状态为 `cancelled` 时：
    - `paid_amount`、`refunded_amount`、`settlement_amount`、`paid_at` 为空
    - `cancel_reason` 不为空
    - `finalized_at` 不为空且 `finalized_at >= created_at`
    - 所有 `order_items.status_code = 'cancelled'`
  - 当订单状态为 `paid` 时：
    - `cancel_reason` 为空
    - `paid_amount >= 0`
    - `paid_amount = payable_amount`
    - `paid_at` 不为空且 `paid_at >= created_at`
    - `refunded_amount` 为空
    - `settlement_amount` 为空
    - `finalized_at` 为空
    - 所有 `order_items.status_code = 'paid'`
  - 当订单状态为 `in_progress` 时：
    - `cancel_reason` 为空
    - `paid_amount >= 0`
    - `paid_amount = payable_amount`
    - `paid_at` 不为空且 `paid_at >= created_at`
    - 可存在退款，因此 `refunded_amount` 可为空也可有值
    - `settlement_amount` 为空
    - `finalized_at` 为空
    - 至少一条 `order_items.status_code` 不属于 `completed` 或 `refunded`
    - 至少一条 `order_items.status_code` 属于 `completed`、`refunded` 或 `ticketed`
  - 当订单状态为 `finished` 时：
    - `cancel_reason` 为空
    - `paid_amount >= 0`
    - `paid_amount = payable_amount`
    - `paid_at` 不为空且 `paid_at >= created_at`
    - 所有 `order_items.status_code` 均属于 `completed` 或 `refunded`
    - `refunded_amount` 为空或满足 `refunded_amount <= paid_amount`
    - 当 `refunded_amount` 不为空时，`orders.refunded_amount = sum(refund_records.amount)`
    - `settlement_amount` 不为空且 `settlement_amount >= 0`
    - `settlement_amount <= goods_amount`
    - `settlement_amount = sum(order_items.settlement_amount)`
    - `finalized_at` 不为空且 `finalized_at >= paid_at`
    - `finalized_at = max(order_items.completed_at, order_items.refunded_at)`
    - 当存在退款时，应存在对应的 `refund_requests` 与 `refund_records` 记录
    - 订单明细在过了对应 `travel_time` 且未退款后进入 `completed`
  - `updated_at >= created_at`

#### `order_items`
订单明细表，按购买单元逐条记录订单对应的具体商品类型、商品对象、金额和出行时间。同一订单下购买两张相同票，应生成两条订单明细。

- `id`：主键 ID。
- `order_id`：订单 ID，关联 `orders.id`。
- `user_id`：下单用户 ID，关联 `users.id`。
- `traveler_id`：出行人 ID，关联 `travelers.id`。
- `product_type_code`：商品类型编码。枚举值：
  - `hotel_room`：酒店房型
  - `scenic_ticket`：景点票种
  - `flight_cabin`：航班舱位
  - `train_seat`：火车席位
  - `bus_seat`：汽车席位
  - `transfer_service`：接送服务
- `product_id`：商品对象 ID。
- `product_name`：商品名称快照。
- `sale_amount`：销售金额。
- `refunded_amount`：退款金额，无退款时为空。
- `settlement_amount`：结算金额，无结算时为空。
- `status_code`：明细状态编码。枚举值：
  - `pending_payment`：待支付
  - `cancelled`：已取消，终态
  - `paid`：已支付
  - `ticketed`：已出票
  - `refunded`：已退款，终态
  - `completed`：已完成，终态
- `travel_time`：出行时间。
- `travel_end_time`：出行结束时间。酒店订单固定存离店时间，其他商品固定为空。
- `cancelled_at`：取消时间。
- `paid_at`：支付时间。
- `refunded_at`：退款时间。
- `completed_at`：完成时间。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - 无
- 外键约束：
  - `fk_order_items_order (order_id -> orders.id)`
  - `fk_order_items_user (user_id -> users.id)`
  - `fk_order_items_order_user ((order_id, user_id) -> orders.(id, user_id))`
  - `fk_order_items_order_type ((order_id, product_type_code) -> orders.(id, order_type_code))`
  - `fk_order_items_traveler (traveler_id -> travelers.id)`
  - `fk_order_items_traveler_user ((traveler_id, user_id) -> travelers.(id, user_id))`
- 业务约束：
  - 同一订单下相同商品按购买单元逐条拆分，不聚合为单条大数量明细。
  - 当 `settlement_amount` 不为空时，满足 `settlement_amount <= sale_amount`
  - `product_type_code` 与 `product_id` 必须匹配对应商品表：
    `hotel_room -> hotel_room_types.id`、`scenic_ticket -> scenic_ticket_types.id`、`flight_cabin -> flight_cabin_inventory.id`、`train_seat -> train_seat_inventory.id`、`bus_seat -> bus_seat_inventory.id`、`transfer_service -> transfer_services.id`
  - `product_type_code = orders.order_type_code`
  - `traveler_id` 按商品类型约束：
    `flight_cabin -> 必填`、`train_seat -> 必填`、`bus_seat -> 必填`、`scenic_ticket -> 可按实名票规则配置为必填或可空`、`hotel_room -> 可空`、`transfer_service -> 可空`
  - 当 `product_type_code = 'hotel_room'` 时：
    - `travel_time` 固定存入住时间
    - `travel_end_time` 固定存离店时间
    - `travel_end_time > travel_time`
  - `user_id = orders.user_id`
  - `traveler_id` 不为空时，`travelers.user_id = user_id`
  - `ticketed` 仅适用于 `flight_cabin`、`train_seat`、`bus_seat`。
  - 各类商品在过了对应 `travel_time` 且未退款后进入 `completed`
  - 当明细状态为 `pending_payment` 时：
    - `cancelled_at`、`paid_at`、`refunded_at`、`completed_at` 为空
    - `sale_amount >= 0`
    - `refunded_amount` 为空
    - `settlement_amount` 为空
    - 对应库存记录执行预占：`available_inventory - 1`、`reserved_inventory + 1`
  - 当明细状态为 `cancelled` 时：
    - `cancelled_at` 不为空且 `cancelled_at >= created_at`
    - `sale_amount >= 0`
    - `paid_at`、`completed_at`、`refunded_at` 为空
    - `refunded_amount` 为空
    - `settlement_amount` 为空
    - 对应库存记录释放预占：`available_inventory + 1`、`reserved_inventory - 1`
  - 当明细状态为 `paid` 时：
    - `cancelled_at`、`completed_at`、`refunded_at` 为空
    - `sale_amount >= 0`
    - `paid_at` 不为空且 `paid_at >= created_at`
    - `refunded_amount` 为空
    - `settlement_amount` 为空
    - 对应库存记录完成转售：`reserved_inventory - 1`、`sold_inventory + 1`
  - 当明细状态为 `ticketed` 时：
    - `cancelled_at`、`refunded_at`、`completed_at` 为空
    - `sale_amount >= 0`
    - `paid_at` 不为空且 `paid_at >= created_at`
    - `refunded_amount` 为空
    - `settlement_amount` 为空
    - 过了 `travel_time` 且未发生退款后，进入 `completed`
  - 当明细状态为 `completed` 时：
    - `cancelled_at` 与 `refunded_at` 为空
    - `sale_amount >= 0`
    - `paid_at` 不为空且 `paid_at >= created_at`
    - `refunded_amount` 为空
    - `settlement_amount >= 0`
    - `completed_at` 不为空且 `completed_at >= paid_at`
    - `completed_at >= travel_time`
    - 机票/火车票/汽车票可由 `ticketed` 在过了 `travel_time` 且未退款后进入 `completed`
    - 酒店/景点/接送服务可由 `paid` 在过了 `travel_time` 且未退款后进入 `completed`
  - 当明细状态为 `refunded` 时：
    - `cancelled_at` 与 `completed_at` 为空
    - `sale_amount >= 0`
    - `paid_at` 不为空且 `paid_at >= created_at`
    - `refunded_amount >= 0` 且 `refunded_amount <= sale_amount`
    - `order_items.refunded_amount = sum(该明细对应退款记录金额)`
    - `refunded_at` 不为空且 `refunded_at >= paid_at`
    - `settlement_amount` 不为空且 `settlement_amount >= 0`
    - `settlement_amount` 表示退款后剩余应结金额
    - 当 `refunded_amount = sale_amount` 时，`settlement_amount = 0`
    - 当 `refunded_amount < sale_amount` 时，`settlement_amount >= 0`
    - 对应库存记录回补库存：`sold_inventory - 1`、`available_inventory + 1`
  - `updated_at >= created_at`

#### `order_coupon_usages`
订单用券记录表，记录订单实际核销的用户优惠券及对应优惠金额。

- `id`：主键 ID。
- `order_id`：订单 ID，关联 `orders.id`。
- `order_item_id`：订单明细 ID，关联 `order_items.id`，为空表示整单级优惠。
- `user_id`：下单用户 ID，关联 `users.id`。
- `template_id`：优惠券模板 ID，关联 `coupon_templates.id`。
- `user_coupon_id`：用户优惠券 ID，关联 `user_coupons.id`。
- `order_type_code`：订单类型编码，冗余存储，需与 `orders.order_type_code` 及 `coupon_templates.applicable_product_type` 一致。
- `discount_amount`：该次用券实际抵扣金额。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_order_coupon_usages_coupon (user_coupon_id)`
- 外键约束：
  - `fk_order_coupon_usages_order (order_id -> orders.id)`
  - `fk_order_coupon_usages_order_item (order_item_id -> order_items.id)`
  - `fk_order_coupon_usages_user (user_id -> users.id)`
  - `fk_order_coupon_usages_order_user ((order_id, user_id) -> orders.(id, user_id))`
  - `fk_order_coupon_usages_order_type ((order_id, order_type_code) -> orders.(id, order_type_code))`
  - `fk_order_coupon_usages_template (template_id -> coupon_templates.id)`
  - `fk_order_coupon_usages_template_type ((template_id, order_type_code) -> coupon_templates.(id, applicable_product_type))`
  - `fk_order_coupon_usages_user_coupon (user_coupon_id -> user_coupons.id)`
  - `fk_order_coupon_usages_coupon_template ((user_coupon_id, template_id) -> user_coupons.(id, template_id))`
  - `fk_order_coupon_usages_coupon_user ((user_coupon_id, user_id) -> user_coupons.(id, user_id))`
- 业务约束：
  - 同一张 `user_coupon` 只能被核销一次
  - `order_type_code = orders.order_type_code`
  - `order_type_code = coupon_templates.applicable_product_type`
  - `discount_amount >= 0`
  - `order_coupon_usages.discount_amount` 参与汇总到 `orders.coupon_discount_amount`

#### `order_promotion_details`
订单促销明细表，记录订单命中的促销活动、促销规则及对应优惠金额。

- `id`：主键 ID。
- `order_id`：订单 ID，关联 `orders.id`。
- `order_item_id`：订单明细 ID，关联 `order_items.id`，为空表示整单级促销。
- `order_type_code`：订单类型编码，冗余存储，需与 `orders.order_type_code` 一致。
- `promotion_id`：促销活动 ID，关联 `promotions.id`。
- `promotion_binding_id`：促销绑定 ID，关联 `promotion_bindings.id`。
- `promotion_rule_id`：促销规则 ID，关联 `promotion_rules.id`，为空表示仅命中活动级优惠。
- `discount_amount`：该次促销实际优惠金额。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_order_promotion_details (order_id, order_item_id, promotion_id, promotion_rule_id)`
- 外键约束：
  - `fk_order_promotion_details_order (order_id -> orders.id)`
  - `fk_order_promotion_details_order_item (order_item_id -> order_items.id)`
  - `fk_order_promotion_details_order_type ((order_id, order_type_code) -> orders.(id, order_type_code))`
  - `fk_order_promotion_details_promotion (promotion_id -> promotions.id)`
  - `fk_order_promotion_details_binding (promotion_binding_id -> promotion_bindings.id)`
  - `fk_order_promotion_details_binding_type ((promotion_binding_id, order_type_code) -> promotion_bindings.(id, product_type_code))`
  - `fk_order_promotion_details_binding_promotion ((promotion_binding_id, promotion_id) -> promotion_bindings.(id, promotion_id))`
  - `fk_order_promotion_details_rule (promotion_rule_id -> promotion_rules.id)`
- 业务约束：
  - `order_type_code = orders.order_type_code`
  - `order_type_code = promotion_bindings.product_type_code`
  - `discount_amount >= 0`
  - `order_promotion_details.discount_amount` 参与汇总到 `orders.marketing_discount_amount`

#### `order_point_usages`
订单积分使用表，记录订单实际抵扣的积分流水及抵扣金额。

- `id`：主键 ID。
- `order_id`：订单 ID，关联 `orders.id`。
- `user_id`：下单用户 ID，关联 `users.id`。
- `point_ledger_id`：积分流水 ID，关联 `member_point_ledger.id`。
- `points_used`：本次订单抵扣的积分数量。
- `discount_amount`：本次积分抵扣金额。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_order_point_usages_ledger (point_ledger_id)`
- 外键约束：
  - `fk_order_point_usages_order (order_id -> orders.id)`
  - `fk_order_point_usages_user (user_id -> users.id)`
  - `fk_order_point_usages_order_user ((order_id, user_id) -> orders.(id, user_id))`
  - `fk_order_point_usages_ledger (point_ledger_id -> member_point_ledger.id)`
  - `fk_order_point_usages_ledger_user ((point_ledger_id, user_id) -> member_point_ledger.(id, user_id))`
- 业务约束：
  - `points_used > 0`
  - `discount_amount >= 0`
  - `user_id = orders.user_id`
  - `user_id = member_point_ledger.user_id`
  - `point_ledger_id` 应对应 `ledger_type_code = 'point_redeem'`
  - `discount_amount` 的币种口径与 `orders.currency_code` 一致
  - `order_point_usages.discount_amount` 参与汇总到 `orders.point_discount_amount`

#### `payments`
支付记录表，存储支付单号、支付方式、支付金额、支付状态和支付时间等资金流水信息。

- `id`：主键 ID。
- `payment_no`：支付单号，业务唯一标识。
- `order_id`：订单 ID，关联 `orders.id`。
- `user_id`：用户 ID，关联 `users.id`。
- `payment_method_code`：支付方式编码。枚举值：
  - `alipay`：支付宝
  - `wechat`：微信支付
  - `unionpay`：银联
- `currency_code`：货币编码，关联 `currencies.currency_code`。
- `amount`：支付金额。
- `status_code`：支付状态编码。枚举值：
  - `pending`：待支付
  - `success`：支付成功
  - `failed`：支付失败
  - `closed`：已关闭
- `paid_at`：支付完成时间。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_payments_no (payment_no)`
- 外键约束：
  - `fk_payments_order (order_id -> orders.id)`
  - `fk_payments_user (user_id -> users.id)`
  - `fk_payments_order_user ((order_id, user_id) -> orders.(id, user_id))`
- 业务约束：
  - `amount >= 0`
  - `amount <= orders.payable_amount`
  - 当支付状态为 `pending` 时：
    - `paid_at` 为空
  - 当支付状态为 `success` 时：
    - `paid_at` 不为空且 `paid_at >= created_at`
    - `paid_at >= orders.created_at`
  - 当支付状态为 `failed` 时：
    - `paid_at` 为空
  - 当支付状态为 `closed` 时：
    - `paid_at` 为空
  - 同一订单成功支付金额汇总满足：`sum(payments.amount where status_code = 'success') = orders.paid_amount`
  - `updated_at >= created_at`

#### `refund_requests`
退款申请表，存储退款类型、申请金额、审核金额、申请时间和处理时间等退款申请信息。

- `id`：主键 ID。
- `refund_request_no`：退款申请单号，业务唯一标识。
- `order_id`：订单 ID，关联 `orders.id`。
- `order_item_id`：订单明细 ID，关联 `order_items.id`。
- `user_id`：用户 ID，关联 `users.id`。
- `requested_amount`：申请退款金额。
- `approved_amount`：审核通过金额。
- `status_code`：退款申请状态编码。枚举值：
  - `pending`：待处理
  - `approved`：审核通过
  - `rejected`：审核驳回
  - `success`：退款完成
- `requested_at`：退款申请时间。
- `processed_at`：退款处理时间。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_refund_requests_no (refund_request_no)`
- 外键约束：
  - `fk_refund_requests_order (order_id -> orders.id)`
  - `fk_refund_requests_order_item (order_item_id -> order_items.id)`
  - `fk_refund_requests_user (user_id -> users.id)`
  - `fk_refund_requests_order_user ((order_id, user_id) -> orders.(id, user_id))`
- 业务约束：
  - `order_item_id` 必须属于 `order_id` 对应订单下的订单明细
  - `requested_amount > 0`
  - `approved_amount <= requested_amount`
  - `requested_at >= order_items.paid_at`
  - `requested_amount <= order_items.sale_amount`
  - 当退款申请状态为 `pending` 时：
    - `processed_at` 为空
    - `approved_amount` 为空
  - 当退款申请状态为 `approved` 时：
    - `processed_at` 不为空且 `processed_at >= requested_at`
    - `approved_amount > 0`
  - 当退款申请状态为 `rejected` 时：
    - `processed_at` 不为空且 `processed_at >= requested_at`
    - `approved_amount` 为空
  - 当退款申请状态为 `success` 时：
    - `processed_at` 不为空且 `processed_at >= requested_at`
    - `approved_amount > 0`
    - 应存在对应的 `refund_records`
  - `updated_at >= created_at`

#### `refund_records`
退款记录表，存储退款单号、退款金额、退款状态、退款处理结果等实际退款流水信息。

- `id`：主键 ID。
- `refund_no`：退款流水号，业务唯一标识。
- `refund_request_id`：退款申请 ID，关联 `refund_requests.id`。
- `order_id`：订单 ID，关联 `orders.id`。
- `order_item_id`：订单明细 ID，关联 `order_items.id`。
- `user_id`：用户 ID，关联 `users.id`。
- `payment_id`：支付记录 ID，关联 `payments.id`。
- `currency_code`：货币编码，关联 `currencies.currency_code`。
- `amount`：退款金额。
- `status_code`：退款状态编码。枚举值：
  - `pending`：退款处理中
  - `success`：退款成功
  - `failed`：退款失败
- `processed_at`：退款完成时间。
- `created_at`：创建时间。
- `updated_at`：更新时间。

- 唯一性约束：
  - `uk_refund_records_no (refund_no)`
  - `uk_refund_records_request (refund_request_id)`
- 外键约束：
  - `fk_refund_records_request (refund_request_id -> refund_requests.id)`
  - `fk_refund_records_order (order_id -> orders.id)`
  - `fk_refund_records_order_item (order_item_id -> order_items.id)`
  - `fk_refund_records_user (user_id -> users.id)`
  - `fk_refund_records_payment (payment_id -> payments.id)`
  - `fk_refund_records_order_user ((order_id, user_id) -> orders.(id, user_id))`
  - `fk_refund_records_payment_order ((payment_id, order_id) -> payments.(id, order_id))`
- 业务约束：
  - `order_item_id` 必须属于 `order_id` 对应订单下的订单明细
  - `amount = refund_requests.approved_amount`
  - 当退款状态为 `pending` 时：
    - `processed_at` 为空
  - 当退款状态为 `success` 时：
    - `processed_at` 不为空且 `processed_at >= refund_requests.requested_at`
  - 当退款状态为 `failed` 时：
    - `processed_at` 不为空且 `processed_at >= refund_requests.requested_at`
  - `updated_at >= created_at`

## 数据生成
### 生成原则
- 分层顺序固定为 `Layer1 -> Layer2 -> Layer3 -> Layer4 -> Layer5 -> Layer6`，后层只能依赖前层已落库数据。
- `seeds` 中已有预定义业务数据的表，直接导入；`coupon_templates` 由 seeds 提供业务配置，时间相关字段由程序补齐后落库。
- 所有编码类字段优先使用“稳定可回放”的规则生成，例如 `HOTEL000001`、`SCENIC000001_ADULT_01`、`ORD0000000001`，保证重复跑批时易于排查。
- 时间字段遵循“主表先、子表后；创建时间先、更新时间后”的原则，保证外键与业务约束同时成立。
- 库存类表统一满足：`available + reserved + sold = total`；价格类表统一满足：`settlement <= sale`。
- 交易链路统一从“商品供给快照”反推订单、支付、退款，避免生成出无法成交或无法退款的脏数据。

### 时间跨度口径
- 时间基准：以脚本运行环境的本地时间为准，取执行当天的当前日期为基准日 `T`，不使用数据库服务器时间作为生成基准。
- 种子导入表：如果时间字段来自 seeds，则以 seeds 内容为准，不在程序层二次改写；但优惠券模板只在 seeds 中维护业务配置，时间字段由程序按营销时间轴生成。
- 商品供给快照：`hotel_room_daily`、`scenic_ticket_daily`、`transfer_capacity_calendar` 的业务日期跨度统一为 `T-730` 到 `T+90`。
- 交通票实例：`flight_departures`、`train_departures`、`bus_departures` 的出发时间跨度统一为 `T-730` 到 `T+90`，不再只覆盖最近一个月。
- 交通票实例状态时效：`arrival_time < T - 12小时` 的历史班次不能继续保持 `scheduled`，应进入 `done` 或少量 `cancelled`；`arrival_time > T` 的未来/进行中班次不能提前标记为 `done`。
- 交通票实例取消时效：`cancelled` 状态表示截至脚本执行时已经取消，`updated_at` 视为取消发生时间，必须满足 `updated_at <= T` 且 `updated_at < departure_time`。
- 交通库存：`flight_cabin_inventory`、`train_seat_inventory`、`bus_seat_inventory` 跟随对应实例时间跨度生成。
- 用户域：`users`、`user_profiles`、`travelers`、`member_accounts`、`member_point_ledger` 的创建时间跨度统一控制在 `T-730` 到 `T`。
- 营销域：`coupon_templates` 从 seeds 导入券种、金额、门槛和适用商品类型；导入后会按 `T-730` 到 `T+90` 的时间轴错开生成滚动有效期窗口，避免所有券集中在同一时间段。`user_coupons` 的发券、使用、过期时间必须落在模板有效期窗口内，每个模板窗口都要产生一批历史使用记录；促销活动本身如果来自 seeds，则以 seeds 时间定义为准。
- 交易域：`orders`、`payments`、`refund_requests`、`refund_records` 的时间跨度统一覆盖 `T-730` 到 `T`；出行时间跟随所引用商品快照或交通实例时间。
- 交易域交通取消联动：机票、火车票、汽车票允许引用已经变为 `cancelled` 的交通实例；若用户在班次取消前已自行取消，则订单保持 `cancelled` 且写入 `finalized_at`；若用户已支付且班次随后取消，则取消后生成退款申请和退款流水，订单明细进入 `refunded`，订单进入 `finished`。
- 交易域下单提前量：`hotel_room` 最多提前 `120` 天，`scenic_ticket` 最多提前 `30` 天，`flight_cabin` 最多提前 `180` 天，`train_seat` 最多提前 `45` 天，`bus_seat` 最多提前 `15` 天，`transfer_service` 最多提前 `30` 天。
- 交易域状态时效：`pending_payment` 只允许保留到订单下最新一笔 `pending` 支付单创建后 `15` 分钟内，超过该窗口的未支付订单应生成或流转为 `cancelled`；`cancelled`、`finished` 等订单终态必须写入 `finalized_at`；`paid`、`ticketed`、`in_progress` 不能在出行时间已过后长期保留，应按商品类型进入 `completed`、`refunded` 或订单级 `finished`。
- 交易域当前时间灰区：机票、火车票、汽车票不从 `T-2小时` 到 `T+6小时` 的未取消班次生成未完结订单，避免长时间全量跑批期间跨过状态时效窗口。
- 交易域完结滞后量：已完成订单应在出行后短窗口内完结，`hotel_room` 最多滞后 `3` 天，`scenic_ticket` 最多滞后 `2` 天，`flight_cabin` 最多滞后 `5` 天，`train_seat` 最多滞后 `3` 天，`bus_seat` 最多滞后 `2` 天，`transfer_service` 最多滞后 `2` 天。
- 交易域退款窗口：退款申请与退款流水应落在支付后且靠近出行时间的窗口内，退款成功时间不得晚于出行后合理窗口，酒店 `7` 天、景点 `3` 天、机票 `14` 天、火车 `7` 天、汽车 `3` 天、接送 `3` 天。
- 所有程序生成的 `updated_at` 都必须满足 `created_at <= updated_at <= T`，不能落到未来。

### 集成执行说明
以下内容按实际执行顺序组织。每个阶段都同时包含：

- 本阶段处理哪些表
- 这些表如何生成
- 具体执行步骤
- 本阶段完成后的检查点

### 阶段 1：Layer1 维度与基础主数据
- 目标：导入所有上游维度表，为商品域和用户域提供稳定引用。
- 处理表：`areas`、`currencies`、`channels`、`transport_hubs`、`suppliers`

表级说明：

- `areas`
  - 来源：直接导入 `seeds/1_dimension/areas.csv`
  - 生成方式：按种子文件构建省/市/区三级结构
  - 关键约束：`area_code` 唯一；`level=1` 无父节点；`level>1` 的父节点层级必须正确
- `currencies`
  - 来源：直接导入 `seeds/1_dimension/currencies.csv`
  - 生成方式：导入预置币种、符号和金额精度
  - 关键约束：`currency_code` 唯一，后续价格表必须引用已存在币种
- `channels`
  - 来源：直接导入 `seeds/1_dimension/channels.csv`
  - 生成方式：导入 App、Web、小程序等渠道定义
  - 关键约束：渠道编码唯一
- `transport_hubs`
  - 来源：直接导入 `seeds/1_dimension/transport_hubs.csv`
  - 生成方式：导入机场、火车站、汽车站及其城市归属
  - 关键约束：`city_area_id` 必须指向 `areas.level = 2`
- `suppliers`
  - 来源：直接导入 `seeds/1_dimension/suppliers.csv`
  - 生成方式：导入酒店、景点、交通、接送等供应商主体
  - 关键约束：`supplier_type_code` 要覆盖全部商品域

Checklist：

- [x] 实现或确认 `SeedImporter` 支持 CSV 读取、`NULL` 识别、批量插入和按表导入。
- [x] 导入 `areas`。
- [x] 导入 `currencies`。
- [x] 导入 `channels`。
- [x] 导入 `transport_hubs`。
- [x] 导入 `suppliers`。
- [x] 执行 Layer1 校验 SQL，检查地区树、枢纽归属和供应商类型覆盖情况。
- [x] 确认不存在孤儿地区、错误父子层级。
- [x] 确认不存在 `transport_hubs.city_area_id` 指向非城市级地区。
- [x] 确认供应商类型至少覆盖 `hotel`、`scenic`、`flight`、`train`、`bus`、`transfer`。

### 阶段 2：Layer2 商品主数据
- 目标：导入商品主数据，并完成商品域完整性检查。
- 处理表：`hotels`、`hotel_room_types`、`hotel_booking_rules`、`scenic_spots`、`scenic_ticket_types`、`scenic_booking_rules`、`flight_routes`、`train_routes`、`bus_routes`、`transfer_services`、`transfer_service_area_rules`

表级说明：

- `hotels`
  - 来源：直接导入 `seeds/2_product/hotels.csv`
  - 生成方式：导入酒店主表
  - 关键约束：`area_id` 为城市；`supplier_id` 必须是酒店供应商
- `hotel_room_types`
  - 来源：直接导入 `seeds/2_product/hotel_room_types.csv`
  - 生成方式：导入房型定义，房型编码遵循 `{hotel_code}_{类别缩写}_{序号}`
  - 关键约束：房型分类和房型名称一致
- `hotel_booking_rules`
  - 来源：直接导入 `seeds/2_product/hotel_booking_rules.csv`
  - 生成方式：导入酒店预订规则
  - 关键约束：与酒店一对一
- `scenic_spots`
  - 来源：直接导入 `seeds/2_product/scenic_spots.csv`
  - 生成方式：导入景点主表
  - 关键约束：`area_id` 为城市；`supplier_id` 为景点供应商
- `scenic_ticket_types`
  - 来源：直接导入 `seeds/2_product/scenic_ticket_types.csv`
  - 生成方式：导入票种定义
  - 关键约束：票种分类、票种名称、景点归属一致
- `scenic_booking_rules`
  - 来源：直接导入 `seeds/2_product/scenic_booking_rules.csv`
  - 生成方式：导入景点预订规则
  - 关键约束：与景点一对一
- `flight_routes`
  - 来源：直接导入 `seeds/2_product/flight_routes.csv`
  - 生成方式：导入航线主数据
  - 关键约束：出发和到达枢纽都必须是机场，且与城市一致
- `train_routes`
  - 来源：直接导入 `seeds/2_product/train_routes.csv`
  - 生成方式：导入火车线路主数据
  - 关键约束：出发和到达枢纽都必须是火车站
- `bus_routes`
  - 来源：直接导入 `seeds/2_product/bus_routes.csv`
  - 生成方式：导入汽车班线主数据
  - 关键约束：出发和到达枢纽都必须是汽车站
- `transfer_services`
  - 来源：直接导入 `seeds/2_product/transfer_services.csv`
  - 生成方式：导入接送服务主表
  - 关键约束：`area_id` 为城市；`supplier_id` 为接送供应商
- `transfer_service_area_rules`
  - 来源：直接导入 `seeds/2_product/transfer_service_area_rules.csv`
  - 生成方式：导入接送区域规则
  - 关键约束：`price_amount >= min_price_amount >= 0`

Checklist：

- [x] 导入 `hotels`。
- [x] 导入 `hotel_room_types`。
- [x] 导入 `hotel_booking_rules`。
- [x] 导入 `scenic_spots`。
- [x] 导入 `scenic_ticket_types`。
- [x] 导入 `scenic_booking_rules`。
- [x] 导入 `flight_routes`。
- [x] 导入 `train_routes`。
- [x] 导入 `bus_routes`。
- [x] 导入 `transfer_services`。
- [x] 导入 `transfer_service_area_rules`。
- [x] 执行酒店组校验。
- [x] 执行景点组校验。
- [x] 执行交通组校验。
- [x] 执行接送组校验。
- [x] 执行 Layer2 汇总统计。
- [x] 确认酒店、房型、规则三张表关系闭环。
- [x] 确认景点、票种、规则三张表关系闭环。
- [x] 确认航线、铁路、班线的枢纽类型和城市关系正确。
- [x] 确认接送服务和区域规则价格关系正确，区域组合不重复。
- [x] 确认酒店、景点、航线、火车、汽车、接送六类商品都非空。

### 阶段 3：Layer3 供给快照
- 目标：基于已存在商品主数据生成库存、价格、班期和运力日历。
- 处理表：`hotel_room_daily`、`scenic_ticket_daily`、`flight_departures`、`flight_cabin_inventory`、`train_departures`、`train_seat_inventory`、`bus_departures`、`bus_seat_inventory`、`transfer_capacity_calendar`

表级说明：

- `hotel_room_daily`
  - 来源：程序生成
  - 生成方式：按房型和日期窗口生成库存与价格，周末和高峰日上浮，业务日期跨度为 `T-730` 到 `T+90`
  - 关键约束：唯一键 `(room_type_id, business_date)`；库存守恒；结算价不高于销售价
- `scenic_ticket_daily`
  - 来源：程序生成
  - 生成方式：按票种和日期窗口生成库存与价格，业务日期跨度为 `T-730` 到 `T+90`
  - 关键约束：唯一键 `(ticket_type_id, business_date)`；库存守恒
- `flight_departures`
  - 来源：程序生成
  - 生成方式：按航线展开历史和未来航班实例，出发时间跨度为 `T-730` 到 `T+90`
  - 关键约束：`arrival_time > departure_time`；历史班次状态为 `done` 或少量 `cancelled`
- `flight_cabin_inventory`
  - 来源：程序生成
  - 生成方式：为每个航班实例生成经济舱、商务舱库存，时间跨度跟随航班实例
  - 关键约束：每个航班每个舱位只一条记录
- `train_departures`
  - 来源：程序生成
  - 生成方式：按线路生成历史和未来班次，出发时间跨度为 `T-730` 到 `T+90`
  - 关键约束：到达时间晚于开车时间；历史班次状态为 `done` 或少量 `cancelled`
- `train_seat_inventory`
  - 来源：程序生成
  - 生成方式：按班次生成二等座、一等座、商务座库存，时间跨度跟随班次实例
  - 关键约束：席别价格梯度和库存守恒同时成立
- `bus_departures`
  - 来源：程序生成
  - 生成方式：按班线生成白天和傍晚班次，出发时间跨度为 `T-730` 到 `T+90`
  - 关键约束：到达时间晚于发车时间；历史班次状态为 `done` 或少量 `cancelled`
- `bus_seat_inventory`
  - 来源：程序生成
  - 生成方式：每个班次生成 `coach` 席位库存，时间跨度跟随班次实例
  - 关键约束：唯一键 `(bus_departure_id, seat_class_code)`
- `transfer_capacity_calendar`
  - 来源：程序生成
  - 生成方式：按服务和日期生成运力日历，业务日期跨度为 `T-730` 到 `T+90`
  - 关键约束：唯一键 `(transfer_service_id, business_date)`；库存守恒

Checklist：

- [x] 生成统一业务日期窗口，覆盖历史、今天、未来。
- [x] 生成 `hotel_room_daily`。
- [x] 生成 `scenic_ticket_daily`。
- [x] 生成 `flight_departures`。
- [x] 生成 `flight_cabin_inventory`。
- [x] 生成 `train_departures`。
- [x] 生成 `train_seat_inventory`。
- [x] 生成 `bus_departures`。
- [x] 生成 `bus_seat_inventory`。
- [x] 生成 `transfer_capacity_calendar`。
- [x] 执行 Layer3 库存、价格和时间顺序校验。
- [x] 确认所有库存表满足 `available + reserved + sold = total`。
- [x] 确认所有价格表满足 `settlement <= sale`。
- [x] 确认所有班期时间满足到达晚于出发。
- [x] 确认所有库存表不存在负数和重复键。

### 阶段 4：Layer4 用户与会员
- 目标：生成用户、实名资料、常用出行人、会员账户和初始积分流水。
- 处理表：`users`、`user_profiles`、`travelers`、`member_accounts`、`member_point_ledger`

表级说明：

- `users`
  - 来源：程序生成
  - 生成方式：从城市级地区轮询注册地，生成昵称、手机号、邮箱、状态和时间字段，创建时间跨度为 `T-730` 到 `T`
  - 关键约束：手机号和邮箱唯一；注册地区必须是城市
- `user_profiles`
  - 来源：程序生成
  - 生成方式：与用户一对一生成实名资料，`residence_city_name` 优先取 `areas.area_full_name`，生成完整行政区名称
  - 关键约束：`user_id` 唯一；时间不早于用户
- `travelers`
  - 来源：程序生成
  - 生成方式：每个用户生成 `1~3` 个常用出行人，其中第一条固定为用户本人，姓名、证件类型、证件号、生日和手机号继承自 `users` 与 `user_profiles`
  - 关键约束：同一用户下证件信息唯一；每个用户都有一条与本人实名资料一致的常用出行人
- `member_accounts`
  - 来源：程序生成
  - 生成方式：先生成成长值，再反推出会员等级
  - 关键约束：会员等级必须由成长值决定
- `member_point_ledger`
  - 来源：程序生成
  - 生成方式：生成注册奖励、调整、过期等基础流水，Layer6 再补交易流水，流水时间跨度为 `T-730` 到 `T`
  - 关键约束：按时间和主键排序后余额连续

Checklist：

- [x] 生成 `users`。
- [x] 生成 `user_profiles`。
- [x] 生成 `travelers`。
- [x] 确认每个用户都有一条本人常用出行人。
- [x] 生成 `member_accounts`。
- [x] 生成初始 `member_point_ledger`。
- [x] 执行用户域唯一键、一对一关系和积分余额连续性校验。
- [x] 确认不存在重复手机号、重复邮箱。
- [x] 确认不存在用户缺资料、缺会员账户。
- [x] 确认交通订单候选用户能取到足够 traveler。
- [x] 确认积分流水累计余额与会员账户余额一致。

### 阶段 5：Layer5 营销
- 目标：准备优惠券模板、用户领券数据和促销活动绑定关系。
- 处理表：`coupon_templates`、`user_coupons`、`promotions`、`promotion_rules`、`promotion_bindings`

表级说明：

- `coupon_templates`
  - 来源：导入 `seeds/5_marketing/coupon_templates.csv` 中的券种、金额、门槛、适用商品类型等业务配置
  - 生成方式：由程序补齐 `valid_from`、`valid_until`、`created_at`、`updated_at`，并将 `active` 模板有效期按滚动窗口错开覆盖 `T-730` 到 `T+90`
  - 关键约束：现金券和折扣券的金额字段规则正确；不同时间段都存在可用模板
- `user_coupons`
  - 来源：程序生成
  - 生成方式：从全量用户池中按模板发券，生成 `available / used / expired` 状态分布，时间跨度受模板有效期约束；每个模板窗口都保留一定比例的 `used`
  - 关键约束：`coupon_code` 唯一；时间窗口合理；历史时间段不能全部没有用券记录
- `promotions`
  - 来源：直接导入 `seeds/5_marketing/promotions.csv`
  - 生成方式：导入促销活动
  - 关键约束：活动时间窗正确
- `promotion_rules`
  - 来源：直接导入 `seeds/5_marketing/promotion_rules.csv`
  - 生成方式：导入促销规则
  - 关键约束：收益类型和 `benefit_payload` 一致
- `promotion_bindings`
  - 来源：直接导入 `seeds/5_marketing/promotion_bindings.csv`
  - 生成方式：导入活动绑定目标
  - 关键约束：绑定目标必须真实存在

Checklist：

- [x] 导入 `coupon_templates` 业务配置并生成模板时间字段。
- [x] 生成 `user_coupons`。
- [x] 导入 `promotions`。
- [x] 导入 `promotion_rules`。
- [x] 导入 `promotion_bindings`。
- [x] 执行模板有效期、发券状态分布和促销绑定目标校验。
- [x] 确认券类型和商品类型映射正确。
- [x] 确认每类商品至少能命中优惠券或促销样本。
- [x] 确认所有促销绑定目标都存在于对应商品域。

### 阶段 6：Layer6 交易闭环
- 目标：基于前五层数据构建完整交易链路，生成订单、支付、退款和交易相关积分流水。
- 处理表：`orders`、`order_items`、`order_coupon_usages`、`order_promotion_details`、`order_point_usages`、`payments`、`refund_requests`、`refund_records`

表级说明：

- `orders`
  - 来源：程序生成
  - 生成方式：从真实商品快照中抽样生成订单，订单创建时间跨度为 `T-730` 到 `T`；酒店订单按入住日和离店日生成 `1~3` 晚入住区间
  - 关键约束：金额汇总闭环；订单类型与商品类型一致；交通订单如引用已取消班次，必须表现为取消后退款闭环；下单提前量符合各商品类型窗口；待支付订单不能超过 `2` 小时
- `order_items`
  - 来源：程序生成
  - 生成方式：保存商品快照、出行人信息、金额分摊和出行时间；酒店明细固定写入 `travel_time = 入住时间`、`travel_end_time = 离店时间`
  - 关键约束：订单明细金额汇总回订单；酒店明细金额按入住晚数汇总；酒店 `travel_end_time > travel_time`；非酒店明细 `travel_end_time` 为空；出行时间早于当前时间的明细不能长期停留在 `paid` 或 `ticketed`
- `order_coupon_usages`
  - 来源：程序生成
  - 生成方式：核销与订单类型匹配、订单时间位于有效期内、且订单金额满足门槛的用户优惠券；已过当前有效期但在历史订单发生时有效的券也会被核销，并在最终状态中更新为 `used`
  - 关键约束：同一张券只能核销一次；全量生成时必须产生优惠券核销记录
- `order_promotion_details`
  - 来源：程序生成
  - 生成方式：记录订单命中的促销活动和规则
  - 关键约束：优惠金额非负，且不超过原价
- `order_point_usages`
  - 来源：程序生成
  - 生成方式：积分抵扣并同步写入 `member_point_ledger(point_redeem)`
  - 关键约束：扣减后积分余额不为负
- `payments`
  - 来源：程序生成
  - 生成方式：为订单生成支付记录，支付时间跨度跟随订单创建时间
  - 关键约束：成功支付金额汇总等于订单已付金额
- `refund_requests`
  - 来源：程序生成
  - 生成方式：对已支付订单明细抽样发起退款申请，申请时间跨度跟随支付时间
  - 关键约束：申请时间晚于支付时间，申请金额不超过明细金额，且应落在靠近出行时间的窗口内
- `refund_records`
  - 来源：程序生成
  - 生成方式：为审核通过或成功的退款申请生成退款流水，退款时间跨度跟随退款申请
  - 关键约束：每个退款申请最多一条退款记录，退款完成时间不能明显晚于出行时间

Checklist：

- [x] 构建交易上下文，汇总用户、积分、traveler、商品快照、优惠券和促销数据。
- [x] 生成 `orders`。
- [x] 生成 `order_items`。
- [x] 确认酒店订单明细写入入住时间和离店时间。
- [x] 生成 `order_coupon_usages`。
- [x] 生成 `order_promotion_details`。
- [x] 生成 `order_point_usages`，并同步补写 `member_point_ledger(point_redeem)`。
- [x] 生成 `payments`。
- [x] 生成 `refund_requests`。
- [x] 生成 `refund_records`。
- [x] 执行订单、支付、退款、积分和优惠金额汇总校验。
- [x] 确认订单金额、支付金额、退款金额、积分抵扣金额、优惠金额全部能对齐。
- [x] 确认酒店订单金额按入住晚数汇总。
- [x] 确认不存在用户积分扣成负数。
- [x] 确认不存在未命中原支付记录的退款流水。
- [x] 确认交通类订单能够正确绑定 traveler。

### 阶段 7：最终验收
- 目标：对全量生成数据进行最终验收，不重复执行 Layer1 到 Layer6 的阶段内校验。
- 验收范围：全库数据

最终验收项：

- 关键表非空：确认所有核心表都已生成数据。
- 全局唯一性：确认编码、单号、券码、实例编码等业务唯一键无重复。
- 跨域外键完整性：确认订单、出行人、支付、退款之间的跨表引用闭环成立。
- 枚举完整性：确认订单、支付、退款、会员等级等枚举字段只取定义内值。
- 故障定位能力：确认关键交易表不存在主键或核心引用字段为空的异常行。
- 执行覆盖度：确认六类商品都已产生订单样本，且配置中的层级表都已真实建表。

Checklist：

- [x] 执行关键表非空校验。
- [x] 执行唯一键校验。
- [x] 执行跨域外键完整性校验。
- [x] 执行枚举完整性校验。
- [x] 执行故障定位字段完整性校验。
- [x] 执行商品覆盖度和层级建表覆盖度校验。
- [x] 确认全量生成后关键表无空表。
- [x] 确认最终验收时核心校验结果全部为 0 异常。

## 接口定义
统一规则：

- 公开浏览类接口不读取用户身份，请求头标记为“无”。
- 用户中心、营销、交易、支付和售后接口统一从请求头 `X-User-Id` 读取演示环境用户标识，并解析为 `currentUserId`。
- 服务端统一校验 `X-User-Id` 是否为合法数字，且对应用户在 `users` 表中真实存在且不为 `inactive`；校验失败直接返回错误。
- 所有写入时间由应用程序生成 `Asia/Shanghai` 本地时间后写入，接口 SQL 不使用数据库当前时间函数。
- 日期字段固定使用 `YYYY-MM-DD`，日期时间字段固定使用 `YYYY-MM-DD HH:mm:ss` 或 `YYYY-MM-DDTHH:mm:ss`。
- 分页参数 `pageNo` 从 `1` 开始，`pageSize` 默认 `20`，服务端最大限制为 `100`。

### 1. 用户中心
面向用户资料、实名信息、常用出行人和会员信息管理。

统一前置规则：

- 所有用户中心接口统一使用 `currentUserId` 作为当前用户身份，不接受前端显式传入 `userId`。

#### 1.1 `GET /api/v1/me`
说明：查询当前用户基础信息和实名资料。

主要关联表：

- `users`
- `user_profiles`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- 无

请求体：

- 无

响应体：

```json
{
  "userId": 10001,
  "nickname": "海边散步的人",
  "phone": "13800000001",
  "email": "user10001@example.com",
  "genderCode": "female",
  "birthDate": "1995-08-16",
  "statusCode": "vip",
  "realName": "张三",
  "identityTypeCode": "id_card",
  "identityNoMasked": "310***********1234",
  "residenceCityName": "上海市 / 浦东新区",
  "occupation": "产品经理"
}
```

接口实现细节：

- 查询条件固定为 `users.id = currentUserId`。
- 查询 `users` 时左联 `user_profiles` 获取实名资料补充信息。
- 若 `user_profiles` 不存在，将实名资料相关字段返回为 `null`。
- `identity_no` 脱敏后返回，避免前台暴露完整证件号码。

#### 1.2 `GET /api/v1/me/travelers`
说明：查询当前用户的常用出行人列表。

主要关联表：

- `travelers`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "travelerId": 30001,
      "travelerName": "张三",
      "identityTypeCode": "id_card",
      "identityNoMasked": "310***********1234",
      "genderCode": "male",
      "birthDate": "1990-05-01",
      "phone": "13800000002",
      "statusCode": "active",
      "createdAt": "2025-01-18 12:00:00",
      "updatedAt": "2025-03-01 10:00:00"
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定为 `travelers.user_id = currentUserId and travelers.status_code = 'active'`。
- `identity_no` 统一脱敏。
- 按 `updated_at desc, id desc` 倒序返回。

#### 1.3 `POST /api/v1/me/travelers`
说明：新增常用出行人。

主要关联表：

- `travelers`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- 无

请求体：

```json
{
  "travelerName": "李四",
  "identityTypeCode": "passport",
  "identityNo": "E12345678",
  "genderCode": "male",
  "birthDate": "1992-11-20",
  "phone": "13800000003"
}
```

响应体：

```json
{
  "travelerId": 30002,
  "travelerName": "李四",
  "identityTypeCode": "passport",
  "identityNoMasked": "E12***678",
  "genderCode": "male",
  "birthDate": "1992-11-20",
  "phone": "13800000003",
  "statusCode": "active",
  "createdAt": "2025-04-18 14:30:00"
}
```

接口实现细节：

- 新增记录时固定写入 `travelers.user_id = currentUserId`。
- 新增前需校验 `(user_id, identity_type_code, identity_no)` 唯一，避免重复创建同一出行人。
- `genderCode` 取值限定为 `male`、`female`。
- 入库前统一对证件号做标准化处理，例如去空格、统一大写。
- 默认写入 `status_code = active`。

#### 1.4 `PUT /api/v1/me/travelers/{travelerId}`
说明：修改常用出行人。

主要关联表：

- `travelers`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `travelerId`：路径参数，必填

请求体：

```json
{
  "travelerName": "李四",
  "identityTypeCode": "passport",
  "identityNo": "E12345678",
  "genderCode": "male",
  "birthDate": "1992-11-20",
  "phone": "13800000003",
  "statusCode": "active"
}
```

响应体：

```json
{
  "travelerId": 30002,
  "travelerName": "李四",
  "identityTypeCode": "passport",
  "identityNoMasked": "E12***678",
  "genderCode": "male",
  "birthDate": "1992-11-20",
  "phone": "13800000003",
  "statusCode": "active",
  "updatedAt": "2025-04-18 14:35:00"
}
```

接口实现细节：

- 先按 `id = travelerId and user_id = currentUserId` 查询出行人，校验该出行人属于当前用户；不存在则直接返回错误。
- 若修改了证件类型或证件号，仍需校验唯一键冲突。
- 若该出行人存在进行中的行程，仅允许修改 `phone`。
- `travelerName`、`identityTypeCode`、`identityNo`、`genderCode`、`birthDate`、`statusCode` 视为受限字段；进行中的行程下不允许修改。
- 若进行中的行程下尝试修改上述受限字段，接口直接返回错误，提示“该出行人有进行中的行程，暂只允许修改手机号，不能修改姓名、证件、性别、出生日期或状态”。

#### 1.5 `DELETE /api/v1/me/travelers/{travelerId}`
说明：删除或停用常用出行人。

主要关联表：

- `travelers`
- `order_items`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `travelerId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "travelerId": 30002,
  "statusCode": "inactive",
  "updatedAt": "2025-04-18 14:40:00"
}
```

接口实现细节：

- 先按 `id = travelerId and user_id = currentUserId` 查询出行人，校验该出行人属于当前用户；不存在则直接返回错误。
- 逻辑停用，更新 `status_code = inactive`，不直接物理删除。
- 删除前需检查该出行人是否存在进行中的订单；若存在，则直接返回错误，提示“该出行人有进行中的行程，暂不可删除”。
- 若仅被历史已完成、已取消或已退款订单引用，继续执行逻辑停用。
- 若重复删除已停用记录，接口幂等返回成功。

#### 1.6 `GET /api/v1/me/member-account`
说明：查询会员等级、积分余额和成长值。

主要关联表：

- `member_accounts`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- 无

请求体：

- 无

响应体：

```json
{
  "userId": 10001,
  "memberLevelCode": "gold",
  "pointsBalance": 16800,
  "totalPoints": 35600,
  "growthValue": 15020,
  "createdAt": "2025-01-15 10:30:00",
  "updatedAt": "2025-04-01 09:20:00"
}
```

接口实现细节：

- 查询条件固定为 `member_accounts.user_id = currentUserId`。
- 会员等级统一以库中 `member_level_code` 为准，接口层不重复计算。
- 若会员账户不存在，视为数据异常，接口直接返回错误，提示“当前用户会员账户不存在”。

#### 1.7 `GET /api/v1/me/point-ledger`
说明：查询积分流水。

主要关联表：

- `member_point_ledger`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`
- `ledgerTypeCode`：可选，积分流水类型；取值 `signup_bonus`、`order_earn`、`order_earn_revoke`、`point_redeem`、`expire`、`admin_adjust`
- `createdFrom`：可选，开始时间，格式 `YYYY-MM-DD HH:mm:ss`，筛选 `created_at >= createdFrom`
- `createdTo`：可选，结束时间，格式 `YYYY-MM-DD HH:mm:ss`，筛选 `created_at <= createdTo`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "ledgerId": 50001,
      "ledgerTypeCode": "order_earn",
      "pointsDelta": 300,
      "balanceAfter": 16800,
      "createdAt": "2025-04-01 11:20:00"
    },
    {
      "ledgerId": 49991,
      "ledgerTypeCode": "point_redeem",
      "pointsDelta": -500,
      "balanceAfter": 16500,
      "createdAt": "2025-03-28 20:15:00"
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 2
}
```

接口实现细节：

- 查询条件固定为 `member_point_ledger.user_id = currentUserId`。
- 按 `created_at desc, id desc` 倒序返回。
- 该接口只返回积分流水基础信息，不返回订单摘要、订单号或其他扩展上下文。

### 2. 商品搜索与详情
该部分是用户侧核心流量入口，覆盖六类商品的列表、详情、库存和价格信息。

#### 2.1 酒店
##### 2.1.1 `GET /api/v1/hotels`
说明：查询酒店列表，支持城市、入住离店、星级、价格区间和关键字筛选。

主要关联表：

- `hotels`
- `hotel_room_types`
- `hotel_room_daily`

请求头：

- 无

请求参数：

- `areaId`：必填，城市地区 ID
- `checkInDate`：必填，入住日期，格式 `YYYY-MM-DD`
- `checkOutDate`：必填，离店日期，格式 `YYYY-MM-DD`
- `starRatingCodes`：可选，星级多选筛选；取值 `3`、`4`、`5`
- `hotelTypeCodes`：可选，酒店类型多选筛选；取值 `luxury`、`business`、`resort`、`boutique`
- `minPrice`：可选，最低价
- `maxPrice`：可选，最高价
- `keyword`：可选，酒店名称关键字
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "hotelId": 20001,
      "hotelCode": "HOTEL000001",
      "hotelName": "上海外滩观景酒店",
      "hotelTypeCode": "business",
      "starRatingCode": "5",
      "areaId": 310100,
      "address": "上海市黄浦区中山东一路1号",
      "summary": "步行可达外滩，适合商务和城市度假。",
      "facilityTags": ["wifi", "parking", "breakfast", "gym"],
      "checkInTime": "14:00:00",
      "checkOutTime": "12:00:00",
      "minSalePriceAmount": 899.00,
      "currencyCode": "CNY",
      "availableRoomCount": 12
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定包含 `hotels.area_id = areaId`、`hotels.status_code = 'active'`。
- 若传入 `starRatingCodes`，筛选条件固定为 `hotels.star_rating_code in (...)`。
- 若传入 `hotelTypeCodes`，筛选条件固定为 `hotels.hotel_type_code in (...)`。
- 入住日期必须早于离店日期；若 `checkInDate >= checkOutDate`，接口直接返回错误。
- 酒店列表只返回在入住日至离店日前一日范围内存在可售房态的酒店。
- 最低价统一取查询日期区间内可售房型的最低 `sale_price_amount`。
- 房型可售判断统一基于 `hotel_room_daily.available_inventory > 0 and hotel_room_daily.status_code = 'active'`。
- 列表按 `minSalePriceAmount asc, hotel_id asc` 排序返回。

##### 2.1.2 `GET /api/v1/hotels/{hotelId}`
说明：查询酒店详情。

主要关联表：

- `hotels`
- `hotel_booking_rules`

请求头：

- 无

请求参数：

- `hotelId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "hotelId": 20001,
  "hotelCode": "HOTEL000001",
  "hotelName": "上海外滩观景酒店",
  "hotelTypeCode": "business",
  "starRatingCode": "5",
  "address": "上海市黄浦区中山东一路1号",
  "latitude": 31.240001,
  "longitude": 121.490001,
  "summary": "步行可达外滩，适合商务和城市度假。",
  "facilityTags": ["wifi", "parking", "breakfast", "gym"],
  "checkInTime": "14:00:00",
  "checkOutTime": "12:00:00",
  "contactPhone": "021-88886666",
  "bookingRule": {
    "holdUntilTime": "18:00:00",
    "minStayNights": 1,
    "maxRoomCount": 3,
    "rulePayload": {
      "cancel_before_hours": 24,
      "support_invoice": true
    }
  }
}
```

接口实现细节：

- 查询条件固定为 `hotels.id = hotelId and hotels.status_code = 'active'`。
- 详情查询统一左联 `hotel_booking_rules`，仅返回 `status_code = 'active'` 的规则记录。
- 若酒店不存在或状态不是 `active`，接口直接返回错误。

##### 2.1.3 `GET /api/v1/hotels/{hotelId}/room-types`
说明：查询酒店房型列表，并返回入住日期区间内的房态房价日历。

主要关联表：

- `hotel_room_types`
- `hotel_room_daily`

请求头：

- 无

请求参数：

- `hotelId`：路径参数，必填
- `checkInDate`：必填，入住日期，格式 `YYYY-MM-DD`
- `checkOutDate`：必填，离店日期，格式 `YYYY-MM-DD`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "roomTypeId": 30001,
      "roomTypeCode": "HOTEL000001_DBL_01",
      "roomTypeName": "大床房",
      "roomTypeCategoryCode": "double",
      "areaSize": 32,
      "maxGuests": 2,
      "amenityPayload": ["window", "desk", "bathroom", "tv"],
      "firstNightSalePriceAmount": 899.00,
      "currencyCode": "CNY",
      "availableRoomCount": 4,
      "calendar": [
        {
          "businessDate": "2025-05-01",
          "availableInventory": 5,
          "salePriceAmount": 899.00,
          "statusCode": "active"
        },
        {
          "businessDate": "2025-05-02",
          "availableInventory": 4,
          "salePriceAmount": 959.00,
          "statusCode": "active"
        }
      ]
    }
  ]
}
```

接口实现细节：

- 查询条件固定为 `hotel_room_types.hotel_id = hotelId and hotel_room_types.status_code = 'active'`。
- 查询日期区间固定为 `business_date >= checkInDate and business_date < checkOutDate`。
- 房型列表只返回在入住日至离店日前一日范围内全程有库存的房型。
- `firstNightSalePriceAmount` 固定取 `checkInDate` 当天的 `sale_price_amount`。
- `availableRoomCount` 固定取查询日期区间内最小 `available_inventory`，作为整段入住期间的可售间数。
- `calendar` 字段按 `businessDate asc` 返回当前房型在入住日期区间内的每日房态房价。
- `calendar` 只返回 `hotel_room_daily.status_code = 'active'` 的记录。

#### 2.2 景点
##### 2.2.1 `GET /api/v1/scenic-spots`
说明：查询景点列表，支持城市、类型、等级、日期和关键字筛选。

主要关联表：

- `scenic_spots`
- `scenic_ticket_types`
- `scenic_ticket_daily`

请求头：

- 无

请求参数：

- `areaId`：必填，城市地区 ID
- `travelDate`：必填，游玩日期，格式 `YYYY-MM-DD`
- `scenicTypeCodes`：可选，景点类型多选筛选；取值 `theme_park`、`museum`、`mountain`、`heritage`、`wetland`、`beach`、`snow`、`forest`、`waterfall`、`cultural_square`、`ancient_town`、`religious`、`theme_water`、`zoo`、`botanical_garden`、`industrial_tourism`、`red_tourism`、`ecological`
- `ratingCodes`：可选，景点等级多选筛选；取值 `5A`、`4A`、`3A`
- `keyword`：可选，景点名称关键字
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "scenicSpotId": 21001,
      "scenicCode": "SCENIC000001",
      "scenicName": "上海海昌海洋公园",
      "scenicTypeCode": "theme_park",
      "ratingCode": "4A",
      "areaId": 310100,
      "address": "上海市浦东新区银飞路166号",
      "summary": "集海洋动物展示、游乐设备和演艺于一体的大型主题公园。",
      "tagPayload": ["family", "theme_park", "parent_child"],
      "openTime": "09:00:00",
      "closeTime": "20:00:00",
      "minSalePriceAmount": 299.00,
      "currencyCode": "CNY",
      "availableTicketCount": 120
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定包含 `scenic_spots.area_id = areaId`、`scenic_spots.status_code = 'active'`。
- 查询日期固定为 `scenic_ticket_daily.business_date = travelDate`。
- 若传入 `scenicTypeCodes`，筛选条件固定为 `scenic_spots.scenic_type_code in (...)`。
- 若传入 `ratingCodes`，筛选条件固定为 `scenic_spots.rating_code in (...)`。
- 景点列表只返回在 `travelDate` 当天存在可售票种的景点。
- 最低价统一取 `travelDate` 当天可售票种的最低 `sale_price_amount`。
- 可售票判断统一基于 `scenic_ticket_daily.available_inventory > 0 and scenic_ticket_daily.status_code = 'active'`。
- 列表按 `minSalePriceAmount asc, scenic_spot_id asc` 排序返回。

##### 2.2.2 `GET /api/v1/scenic-spots/{scenicSpotId}`
说明：查询景点详情。

主要关联表：

- `scenic_spots`
- `scenic_booking_rules`

请求头：

- 无

请求参数：

- `scenicSpotId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "scenicSpotId": 21001,
  "scenicCode": "SCENIC000001",
  "scenicName": "上海海昌海洋公园",
  "scenicTypeCode": "theme_park",
  "ratingCode": "4A",
  "address": "上海市浦东新区银飞路166号",
  "latitude": 31.143001,
  "longitude": 121.939001,
  "summary": "集海洋动物展示、游乐设备和演艺于一体的大型主题公园。",
  "tagPayload": ["family", "theme_park", "parent_child"],
  "openTime": "09:00:00",
  "closeTime": "20:00:00",
  "bookingRule": {
    "latestBookingTime": "18:00:00",
    "rulePayload": {
      "support_refund": true,
      "refund_rule": "T-1 free"
    }
  }
}
```

接口实现细节：

- 查询条件固定为 `scenic_spots.id = scenicSpotId and scenic_spots.status_code = 'active'`。
- 详情查询统一左联 `scenic_booking_rules`，仅返回 `status_code = 'active'` 的规则记录。
- 若景点不存在或状态不是 `active`，接口直接返回错误。

##### 2.2.3 `GET /api/v1/scenic-spots/{scenicSpotId}/ticket-types`
说明：查询景点票种列表，并返回游玩日期对应的价格和库存信息。

主要关联表：

- `scenic_ticket_types`
- `scenic_ticket_daily`

请求头：

- 无

请求参数：

- `scenicSpotId`：路径参数，必填
- `travelDate`：必填，游玩日期，格式 `YYYY-MM-DD`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "ticketTypeId": 31001,
      "ticketTypeCode": "SCENIC000001_ADULT_01",
      "ticketTypeName": "成人票",
      "ticketCategoryCode": "adult",
      "benefitPayload": {
        "enter_times": 1,
        "refund_rule": "T-1 free"
      },
      "salePriceAmount": 299.00,
      "currencyCode": "CNY",
      "availableTicketCount": 120,
      "calendar": [
        {
          "businessDate": "2025-05-01",
          "availableInventory": 120,
          "salePriceAmount": 299.00,
          "statusCode": "active"
        }
      ]
    }
  ]
}
```

接口实现细节：

- 查询条件固定为 `scenic_ticket_types.scenic_spot_id = scenicSpotId and scenic_ticket_types.status_code = 'active'`。
- 查询日期固定为 `scenic_ticket_daily.business_date = travelDate`。
- 票种列表只返回在 `travelDate` 当天有可售库存的票种。
- `salePriceAmount` 固定取 `travelDate` 当天的 `sale_price_amount`。
- `availableTicketCount` 固定取 `travelDate` 当天的 `available_inventory`。
- `calendar` 字段固定返回当前票种在 `travelDate` 当天的库存与价格明细。
- `calendar` 只返回 `scenic_ticket_daily.status_code = 'active'` 的记录。

#### 2.3 机票
##### 2.3.1 `GET /api/v1/flights/search`
说明：查询机票搜索结果列表。

主要关联表：

- `flight_routes`
- `flight_departures`
- `flight_cabin_inventory`

请求头：

- 无

请求参数：

- `departureAreaId`：必填，出发城市地区 ID
- `arrivalAreaId`：必填，到达城市地区 ID
- `departureDate`：必填，出发日期，格式 `YYYY-MM-DD`
- `cabinClassCodes`：可选，舱位等级多选筛选；取值 `economy`、`business`
- `airlineCodes`：可选，航司多选筛选；取值 `MU`、`CA`、`CZ`、`HU`、`HO`、`3U`、`FM`、`9C`、`BK`、`KN`、`SC`、`TV`、`EU`、`G5`、`JR`、`NS`、`JD`、`ZH`、`PN`、`CO`
- `departureTimeFrom`：可选，起飞时间下限，格式 `HH:mm:ss`
- `departureTimeTo`：可选，起飞时间上限，格式 `HH:mm:ss`
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "departureId": 41001,
      "departureInstanceCode": "FLIGHT_DEMO_0001",
      "flightNo": "MU5101",
      "airlineCode": "MU",
      "departureAreaId": 310100,
      "arrivalAreaId": 110100,
      "departureHubName": "上海虹桥国际机场",
      "arrivalHubName": "北京首都国际机场",
      "departureTime": "2025-05-01 08:30:00",
      "arrivalTime": "2025-05-01 10:45:00",
      "durationMinutes": 135,
      "minSalePriceAmount": 680.00,
      "currencyCode": "CNY",
      "availableCabinClasses": ["economy", "business"]
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定包含 `flight_routes.departure_area_id = departureAreaId`、`flight_routes.arrival_area_id = arrivalAreaId`、`flight_routes.status_code = 'active'`。
- 查询日期固定为 `date(flight_departures.departure_time) = departureDate`。
- 航班实例只返回 `flight_departures.status_code = 'scheduled'` 的记录。
- 若传入 `cabinClassCodes`，筛选条件固定为 `flight_cabin_inventory.cabin_class_code in (...)`。
- 若传入 `airlineCodes`，筛选条件固定为 `flight_routes.airline_code in (...)`。
- 机票搜索结果只返回至少存在一个可售舱位的航班实例。
- 可售舱位判断统一基于 `flight_cabin_inventory.available_inventory > 0 and flight_cabin_inventory.status_code = 'active'`。
- 最低价统一取当前航班实例下可售舱位的最低 `sale_price_amount`。
- 列表按 `departure_time asc, departure_id asc` 排序返回。

##### 2.3.2 `GET /api/v1/flights/{departureId}`
说明：查询航班详情及舱位商品信息。

主要关联表：

- `flight_departures`
- `flight_routes`
- `flight_cabin_inventory`

请求头：

- 无

请求参数：

- `departureId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "departureId": 41001,
  "departureInstanceCode": "FLIGHT_DEMO_0001",
  "flightNo": "MU5101",
  "airlineCode": "MU",
  "departureHubName": "上海虹桥国际机场",
  "arrivalHubName": "北京首都国际机场",
  "departureTime": "2025-05-01 08:30:00",
  "arrivalTime": "2025-05-01 10:45:00",
  "durationMinutes": 135,
  "rulePayload": {
    "free_checked_baggage": {
      "weight": 23,
      "piece": 1
    },
    "free_cabin_baggage": {
      "weight": 5,
      "size": "40x30x20"
    },
    "meal": true
  },
  "cabins": [
    {
      "cabinClassCode": "economy",
      "salePriceAmount": 680.00,
      "currencyCode": "CNY",
      "availableInventory": 18,
      "statusCode": "active"
    },
    {
      "cabinClassCode": "business",
      "salePriceAmount": 1580.00,
      "currencyCode": "CNY",
      "availableInventory": 4,
      "statusCode": "active"
    }
  ]
}
```

接口实现细节：

- 查询条件固定为 `flight_departures.id = departureId and flight_departures.status_code = 'scheduled'`。
- 详情查询统一关联 `flight_routes`，并要求 `flight_routes.status_code = 'active'`。
- `cabins` 只返回 `flight_cabin_inventory.status_code = 'active'` 的记录。
- 舱位列表按 `sale_price_amount asc, cabin_class_code asc` 排序返回。
- 若航班实例不存在、状态不是 `scheduled`，或其对应航线状态不是 `active`，接口直接返回错误。

#### 2.4 火车票
##### 2.4.1 `GET /api/v1/trains/search`
说明：查询火车票搜索结果列表。

主要关联表：

- `train_routes`
- `train_departures`
- `train_seat_inventory`

请求头：

- 无

请求参数：

- `departureAreaId`：必填，出发城市地区 ID
- `arrivalAreaId`：必填，到达城市地区 ID
- `departureDate`：必填，出发日期，格式 `YYYY-MM-DD`
- `seatClassCodes`：可选，席位等级多选筛选；取值 `second_class`、`first_class`、`business`
- `trainNo`：可选，车次号关键字
- `departureTimeFrom`：可选，发车时间下限，格式 `HH:mm:ss`
- `departureTimeTo`：可选，发车时间上限，格式 `HH:mm:ss`
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "departureId": 51001,
      "departureInstanceCode": "TRAIN_DEMO_0001",
      "trainNo": "G102",
      "departureAreaId": 310100,
      "arrivalAreaId": 320100,
      "departureHubName": "上海虹桥站",
      "arrivalHubName": "南京南站",
      "departureTime": "2025-05-01 09:00:00",
      "arrivalTime": "2025-05-01 10:35:00",
      "durationMinutes": 95,
      "minSalePriceAmount": 129.00,
      "currencyCode": "CNY",
      "availableSeatClasses": ["second_class", "first_class"]
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定包含 `train_routes.departure_area_id = departureAreaId`、`train_routes.arrival_area_id = arrivalAreaId`、`train_routes.status_code = 'active'`。
- 查询日期固定为 `date(train_departures.departure_time) = departureDate`。
- 车次实例只返回 `train_departures.status_code = 'scheduled'` 的记录。
- 若传入 `seatClassCodes`，筛选条件固定为 `train_seat_inventory.seat_class_code in (...)`。
- 若传入 `trainNo`，筛选条件固定为 `train_routes.train_no like ...`。
- 火车票搜索结果只返回至少存在一个可售席位的车次实例。
- 可售席位判断统一基于 `train_seat_inventory.available_inventory > 0 and train_seat_inventory.status_code = 'active'`。
- 最低价统一取当前车次实例下可售席位的最低 `sale_price_amount`。
- 列表按 `departure_time asc, departure_id asc` 排序返回。

##### 2.4.2 `GET /api/v1/trains/{departureId}`
说明：查询车次详情及席位商品信息。

主要关联表：

- `train_departures`
- `train_routes`
- `train_seat_inventory`

请求头：

- 无

请求参数：

- `departureId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "departureId": 51001,
  "departureInstanceCode": "TRAIN_DEMO_0001",
  "trainNo": "G102",
  "departureHubName": "上海虹桥站",
  "arrivalHubName": "南京南站",
  "departureTime": "2025-05-01 09:00:00",
  "arrivalTime": "2025-05-01 10:35:00",
  "durationMinutes": 95,
  "seats": [
    {
      "seatClassCode": "second_class",
      "salePriceAmount": 129.00,
      "currencyCode": "CNY",
      "availableInventory": 56,
      "statusCode": "active"
    },
    {
      "seatClassCode": "first_class",
      "salePriceAmount": 219.00,
      "currencyCode": "CNY",
      "availableInventory": 12,
      "statusCode": "active"
    }
  ]
}
```

接口实现细节：

- 查询条件固定为 `train_departures.id = departureId and train_departures.status_code = 'scheduled'`。
- 详情查询统一关联 `train_routes`，并要求 `train_routes.status_code = 'active'`。
- `seats` 只返回 `train_seat_inventory.status_code = 'active'` 的记录。
- 席位列表按 `sale_price_amount asc, seat_class_code asc` 排序返回。
- 若车次实例不存在、状态不是 `scheduled`，或其对应线路状态不是 `active`，接口直接返回错误。

#### 2.5 汽车票
##### 2.5.1 `GET /api/v1/buses/search`
说明：查询汽车票搜索结果列表。

主要关联表：

- `bus_routes`
- `bus_departures`
- `bus_seat_inventory`

请求头：

- 无

请求参数：

- `departureAreaId`：必填，出发城市地区 ID
- `arrivalAreaId`：必填，到达城市地区 ID
- `departureDate`：必填，出发日期，格式 `YYYY-MM-DD`
- `routeName`：可选，班线名称关键字
- `departureTimeFrom`：可选，发车时间下限，格式 `HH:mm:ss`
- `departureTimeTo`：可选，发车时间上限，格式 `HH:mm:ss`
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "departureId": 61001,
      "departureInstanceCode": "BUS_DEMO_0001",
      "routeName": "上海南站-苏州汽车北站",
      "departureAreaId": 310100,
      "arrivalAreaId": 320500,
      "departureHubName": "上海长途客运南站",
      "arrivalHubName": "苏州汽车北站",
      "departureTime": "2025-05-01 08:20:00",
      "arrivalTime": "2025-05-01 10:50:00",
      "durationMinutes": 150,
      "salePriceAmount": 68.00,
      "currencyCode": "CNY",
      "availableInventory": 23
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定包含 `bus_routes.departure_area_id = departureAreaId`、`bus_routes.arrival_area_id = arrivalAreaId`、`bus_routes.status_code = 'active'`。
- 查询日期固定为 `date(bus_departures.departure_time) = departureDate`。
- 班次实例只返回 `bus_departures.status_code = 'scheduled'` 的记录。
- 若传入 `routeName`，筛选条件固定为 `bus_routes.route_name like ...`。
- 汽车票搜索结果只返回存在可售席位的班次实例。
- 可售席位判断统一基于 `bus_seat_inventory.available_inventory > 0 and bus_seat_inventory.status_code = 'active'`。
- 汽车票商品统一返回 `seat_class_code = 'coach'` 的库存与价格。
- 列表按 `departure_time asc, departure_id asc` 排序返回。

##### 2.5.2 `GET /api/v1/buses/{departureId}`
说明：查询汽车班次详情及席位商品信息。

主要关联表：

- `bus_departures`
- `bus_routes`
- `bus_seat_inventory`

请求头：

- 无

请求参数：

- `departureId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "departureId": 61001,
  "departureInstanceCode": "BUS_DEMO_0001",
  "routeName": "上海南站-苏州汽车北站",
  "departureHubName": "上海长途客运南站",
  "arrivalHubName": "苏州汽车北站",
  "departureTime": "2025-05-01 08:20:00",
  "arrivalTime": "2025-05-01 10:50:00",
  "durationMinutes": 150,
  "seats": [
    {
      "seatClassCode": "coach",
      "salePriceAmount": 68.00,
      "currencyCode": "CNY",
      "availableInventory": 23,
      "statusCode": "active"
    }
  ]
}
```

接口实现细节：

- 查询条件固定为 `bus_departures.id = departureId and bus_departures.status_code = 'scheduled'`。
- 详情查询统一关联 `bus_routes`，并要求 `bus_routes.status_code = 'active'`。
- `seats` 只返回 `bus_seat_inventory.status_code = 'active'` 的记录。
- 若班次实例不存在、状态不是 `scheduled`，或其对应班线状态不是 `active`，接口直接返回错误。

#### 2.6 接送服务
##### 2.6.1 `GET /api/v1/transfers`
说明：查询接送服务列表。

主要关联表：

- `transfer_services`
- `transfer_capacity_calendar`

请求头：

- 无

请求参数：

- `areaId`：必填，服务城市地区 ID
- `businessDate`：必填，服务日期，格式 `YYYY-MM-DD`
- `serviceTypeCodes`：可选，服务类型多选筛选；取值 `airport_pickup`、`airport_dropoff`、`charter_daily`、`station_transfer`
- `vehicleTypeCodes`：可选，车型多选筛选；取值 `economy`、`comfort`、`business`、`van`
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "serviceId": 71001,
      "serviceCode": "TRANSFER000001",
      "serviceName": "上海浦东机场接机",
      "serviceTypeCode": "airport_pickup",
      "areaId": 310100,
      "vehicleTypeCode": "business",
      "passengerCapacity": 5,
      "availableInventory": 18
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定包含 `transfer_services.area_id = areaId`、`transfer_services.status_code = 'active'`。
- 查询日期固定为 `transfer_capacity_calendar.business_date = businessDate`。
- 若传入 `serviceTypeCodes`，筛选条件固定为 `transfer_services.service_type_code in (...)`。
- 若传入 `vehicleTypeCodes`，筛选条件固定为 `transfer_services.vehicle_type_code in (...)`。
- 服务列表只返回在 `businessDate` 当天存在可售运力的服务。
- 可售运力判断统一基于 `transfer_capacity_calendar.available_inventory > 0 and transfer_capacity_calendar.status_code = 'active'`。
- 列表按 `vehicle_type_code asc, service_id asc` 排序返回。

##### 2.6.2 `GET /api/v1/transfers/{serviceId}`
说明：查询接送服务详情。

主要关联表：

- `transfer_services`

请求头：

- 无

请求参数：

- `serviceId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "serviceId": 71001,
  "serviceCode": "TRANSFER000001",
  "serviceName": "上海浦东机场接机",
  "serviceTypeCode": "airport_pickup",
  "areaId": 310100,
  "vehicleTypeCode": "business",
  "passengerCapacity": 5
}
```

接口实现细节：

- 查询条件固定为 `transfer_services.id = serviceId and transfer_services.status_code = 'active'`。
- 若服务不存在或状态不是 `active`，接口直接返回错误。

##### 2.6.3 `GET /api/v1/transfers/{serviceId}/pricing`
说明：按上车城市、下车城市和服务日期查询接送服务价格与库存。

主要关联表：

- `transfer_service_area_rules`
- `transfer_capacity_calendar`
- `transfer_services`

请求头：

- 无

请求参数：

- `serviceId`：路径参数，必填
- `pickupAreaId`：必填，上车地区 ID
- `dropoffAreaId`：必填，下车地区 ID
- `businessDate`：必填，服务日期，格式 `YYYY-MM-DD`

请求体：

- 无

响应体：

```json
{
  "serviceId": 71001,
  "pickupAreaId": 310115,
  "dropoffAreaId": 310110,
  "businessDate": "2025-05-01",
  "vehicleTypeCode": "business",
  "passengerCapacity": 5,
  "salePriceAmount": 188.00,
  "currencyCode": "CNY",
  "availableInventory": 18,
  "rulePayload": [
    {
      "type": "night_fee",
      "amount": 20,
      "condition": "22:00-06:00"
    }
  ],
  "statusCode": "active"
}
```

接口实现细节：

- 查询条件固定为 `transfer_services.id = serviceId and transfer_services.status_code = 'active'`。
- 区域价格规则固定按 `transfer_service_area_rules.transfer_service_id = serviceId and pickup_area_id = pickupAreaId and dropoff_area_id = dropoffAreaId` 查询。
- 运力查询固定按 `transfer_capacity_calendar.transfer_service_id = serviceId and business_date = businessDate` 查询。
- 价格与库存结果只返回 `transfer_service_area_rules.status_code = 'active'` 且 `transfer_capacity_calendar.status_code = 'active'` 的记录。
- 若不存在匹配的区域价格规则、服务日期运力记录或服务状态无效，接口直接返回错误。

### 3. 营销与优惠
面向领券、查券等场景。

#### 3.1 `GET /api/v1/coupon-templates/available`
说明：查询当前用户可领取的优惠券模板列表。

主要关联表：

- `coupon_templates`
- `user_coupons`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `productTypeCode`：可选，商品类型；取值 `hotel_room`、`scenic_ticket`、`flight_cabin`、`train_seat`、`bus_seat`、`transfer_service`
- `supplierId`：可选，供应商 ID
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "templateId": 81001,
      "templateCode": "CPN_DEMO_0001",
      "templateName": "酒店满500减50",
      "couponTypeCode": "HOTEL_ROOM_CASH",
      "applicableProductType": "hotel_room",
      "minSpendAmount": 500.00,
      "discountAmount": 50.00,
      "maxDiscountAmount": null,
      "validFrom": "2025-05-01 00:00:00",
      "validUntil": "2025-05-31 23:59:59",
      "perUserLimit": 1,
      "receivedCount": 0
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定为 `coupon_templates.status_code = 'active'`，且当前时间位于 `valid_from` 与 `valid_until` 之间。
- 若传入 `productTypeCode`，筛选条件固定为 `coupon_templates.applicable_product_type = productTypeCode`。
- 若传入 `supplierId`，筛选条件固定为 `coupon_templates.applicable_supplier_id = supplierId or applicable_supplier_id is null`。
- `receivedCount` 固定按当前用户已领取该模板的 `user_coupons` 数量统计。
- 只返回当前用户仍可领取的模板，即 `receivedCount < per_user_limit`。

#### 3.2 `GET /api/v1/coupons`
说明：查询当前用户已领取的优惠券列表。

主要关联表：

- `user_coupons`
- `coupon_templates`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `statusCode`：可选，优惠券状态；取值 `available`、`used`、`expired`
- `productTypeCode`：可选，商品类型；取值 `hotel_room`、`scenic_ticket`、`flight_cabin`、`train_seat`、`bus_seat`、`transfer_service`
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "userCouponId": 82001,
      "couponCode": "UC_DEMO_0001",
      "templateId": 81001,
      "templateName": "酒店满500减50",
      "couponTypeCode": "HOTEL_ROOM_CASH",
      "applicableProductType": "hotel_room",
      "minSpendAmount": 500.00,
      "discountAmount": 50.00,
      "maxDiscountAmount": null,
      "validFrom": "2025-05-01 00:00:00",
      "validUntil": "2025-05-31 23:59:59",
      "statusCode": "available",
      "usedAt": null
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定为 `user_coupons.user_id = currentUserId`。
- 若传入 `statusCode`，筛选条件固定为 `user_coupons.status_code = statusCode`。
- 若传入 `productTypeCode`，筛选条件固定为 `coupon_templates.applicable_product_type = productTypeCode`。
- 列表按 `valid_until asc, id desc` 排序返回。

#### 3.3 `POST /api/v1/coupons/receive`
说明：领取优惠券。

主要关联表：

- `coupon_templates`
- `user_coupons`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- 无

请求体：

```json
{
  "templateId": 81001
}
```

响应体：

```json
{
  "userCouponId": 82001,
  "couponCode": "UC_DEMO_0001",
  "templateId": 81001,
  "statusCode": "available",
  "validFrom": "2025-05-01 00:00:00",
  "validUntil": "2025-05-31 23:59:59"
}
```

接口实现细节：

- 先按 `templateId` 查询优惠券模板，校验模板状态为 `active` 且当前时间在有效发放期内。
- 再统计当前用户已领取数量，若已达到 `per_user_limit`，接口直接返回错误。
- 领取成功后创建一条 `user_coupons` 记录，金额、门槛和有效期直接继承模板。
- 新券状态固定写入 `status_code = 'available'`。

### 4. 交易与支付
面向订单创建、订单查询、支付发起和取消。

#### 4.1 `POST /api/v1/orders`
说明：创建订单。

主要关联表：

- `orders`
- `order_items`
- `order_coupon_usages`
- `order_promotion_details`
- `order_point_usages`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- 无

请求体：

```json
{
  "orderTypeCode": "hotel_room",
  "sourceChannelCode": "app",
  "currencyCode": "CNY",
  "items": [
    {
      "productTypeCode": "hotel_room",
      "productId": 20001,
      "productName": "上海外滩观景酒店-大床房",
      "quantity": 1,
      "checkInDate": "2025-05-01",
      "checkOutDate": "2025-05-03",
      "travelerIds": [30001]
    }
  ],
  "userCouponIds": [82001],
  "usePoints": true
}
```

响应体：

```json
{
  "orderId": 91001,
  "orderNo": "TR_DEMO_0001",
  "orderTypeCode": "hotel_room",
  "statusCode": "pending_payment",
  "goodsAmount": 1798.00,
  "marketingDiscountAmount": 100.00,
  "couponDiscountAmount": 50.00,
  "pointDiscountAmount": 20.00,
  "payableAmount": 1628.00,
  "createdAt": "2025-05-01 10:00:00"
}
```

接口实现细节：

- 创建订单前服务端固定重新执行一次商品价格、优惠券、促销和积分的完整校验与重算。
- 当 `orderTypeCode = 'hotel_room'` 时，订单明细固定使用 `checkInDate` 和 `checkOutDate` 计算整段入住金额，不使用 `travelTime` 单晚计价。
- 订单所属用户固定写入 `orders.user_id = currentUserId`。
- 订单主表、订单明细、用券记录、促销明细和积分使用记录统一在一个事务内落库。
- 若任一商品库存不足、优惠券不可用或积分余额不足，接口直接返回错误，订单不得落库。
- 创建成功后，订单初始状态固定写入待支付状态。

#### 4.2 `GET /api/v1/orders`
说明：查询当前用户订单列表。

主要关联表：

- `orders`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `statusCode`：可选，订单状态；取值 `pending_payment`、`cancelled`、`paid`、`in_progress`、`finished`
- `orderTypeCode`：可选，订单类型；取值 `hotel_room`、`scenic_ticket`、`flight_cabin`、`train_seat`、`bus_seat`、`transfer_service`
- `createdFrom`：可选，开始时间，筛选 `created_at >= createdFrom` 的订单
- `createdTo`：可选，结束时间，筛选 `created_at <= createdTo` 的订单
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "orderId": 91001,
      "orderNo": "TR_DEMO_0001",
      "orderTypeCode": "hotel_room",
      "statusCode": "pending_payment",
      "goodsAmount": 1798.00,
      "payableAmount": 1628.00,
      "createdAt": "2025-05-01 10:00:00"
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定为 `orders.user_id = currentUserId`。
- 若传入 `statusCode`，筛选条件固定为 `orders.status_code = statusCode`。
- 若传入 `orderTypeCode`，筛选条件固定为 `orders.order_type_code = orderTypeCode`。
- 列表按 `created_at desc, id desc` 倒序返回。

#### 4.3 `GET /api/v1/orders/{orderId}`
说明：查询订单详情，返回订单主信息、订单明细、支付信息和营销信息。

主要关联表：

- `orders`
- `order_items`
- `order_coupon_usages`
- `order_promotion_details`
- `order_point_usages`
- `payments`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `orderId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "orderId": 91001,
  "orderNo": "TR_DEMO_0001",
  "orderTypeCode": "hotel_room",
  "statusCode": "pending_payment",
  "currencyCode": "CNY",
  "goodsAmount": 1798.00,
  "marketingDiscountAmount": 100.00,
  "couponDiscountAmount": 50.00,
  "pointDiscountAmount": 20.00,
  "payableAmount": 1628.00,
  "paidAmount": null,
  "refundedAmount": null,
  "sourceChannelCode": "app",
  "createdAt": "2025-05-01 10:00:00",
  "items": [
    {
      "orderItemId": 92001,
      "productTypeCode": "hotel_room",
      "productId": 20001,
      "productName": "上海外滩观景酒店-大床房",
      "saleAmount": 1798.00,
      "statusCode": "pending_payment",
      "travelTime": "2025-05-01 00:00:00",
      "travelEndTime": "2025-05-03 00:00:00"
    }
  ],
  "couponUsages": [
    {
      "userCouponId": 82001,
      "discountAmount": 50.00
    }
  ],
  "promotionDetails": [
    {
      "promotionId": 83001,
      "discountAmount": 100.00
    }
  ],
  "pointUsage": {
    "pointsUsed": 200,
    "discountAmount": 20.00
  },
  "payments": []
}
```

接口实现细节：

- 查询条件固定为 `orders.id = orderId and orders.user_id = currentUserId`。
- 订单详情固定聚合返回订单主信息、订单明细、用券信息、促销信息、积分抵扣信息和支付记录。
- 若订单不存在或不属于当前用户，接口直接返回错误。

#### 4.4 `POST /api/v1/orders/{orderId}/cancel`
说明：取消订单。

主要关联表：

- `orders`
- `order_items`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `orderId`：路径参数，必填

请求体：

```json
{
  "cancelReason": "行程变更"
}
```

响应体：

```json
{
  "orderId": 91001,
  "statusCode": "cancelled",
  "cancelReason": "行程变更",
  "updatedAt": "2025-05-01 10:20:00"
}
```

接口实现细节：

- 先按 `orderId` 查询订单，校验订单属于当前用户；不存在则直接返回错误。
- 只允许取消未支付且未关闭的订单。
- 取消订单时统一更新 `orders.status_code` 和对应 `order_items.status_code`。
- 取消成功后若存在已占用库存、优惠券或积分，统一执行回退。

#### 4.5 `POST /api/v1/orders/{orderId}/payments`
说明：发起支付。

兼容路径：`POST /api/v1/orders/{orderId}/pay` 保留为旧客户端兼容入口，内部处理逻辑与本接口一致。

主要关联表：

- `payments`
- `orders`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `orderId`：路径参数，必填

请求体：

```json
{
  "paymentMethodCode": "alipay",
  "clientType": "app"
}
```

响应体：

```json
{
  "paymentId": 93001,
  "paymentNo": "PAY_DEMO_0001",
  "orderId": 91001,
  "amount": 1628.00,
  "statusCode": "pending",
  "paymentMethodCode": "alipay",
  "paymentPayload": {
    "payToken": "mock_pay_token_93001",
    "expireTime": "2025-05-01 10:45:00",
    "clientType": "app"
  }
}
```

接口实现细节：

- 先按 `orderId` 查询订单，校验订单属于当前用户且订单状态为待支付。
- 固定校验订单 `payable_amount > 0`；若应付金额小于等于 `0`，接口直接返回错误。
- 若订单下已存在状态为待支付的支付记录，直接返回原支付记录和支付拉起参数，不重复创建新支付单。
- 支付记录固定写入 `payments.user_id = currentUserId`。
- 发起支付时创建一条支付记录，初始状态固定写入待支付状态，并生成唯一 `payment_no`。
- 演示环境不接入真实支付渠道，创建支付记录后固定返回模拟支付拉起参数 `paymentPayload`。
- 该接口只创建或复用 `pending` 支付记录，并返回模拟支付拉起参数；支付成功状态流转不在该接口内处理。
- 若订单已支付、已取消或已关闭，接口直接返回错误。

#### 4.6 `POST /api/v1/payments/callback`
说明：处理支付渠道回调，接收支付成功、支付失败或支付关闭结果。

主要关联表：

- `payments`
- `orders`
- `order_items`
- `member_accounts`
- `member_point_ledger`

请求头：

- `X-Demo-Payment-Signature: <signature>`：演示环境支付回调签名

请求参数：

- 无

请求体：

```json
{
  "paymentNo": "PAY_DEMO_0001",
  "orderId": 91001,
  "paymentMethodCode": "alipay",
  "amount": 1628.00,
  "statusCode": "success",
  "paidAt": "2025-05-01 10:30:00",
  "channelTradeNo": "MOCK_ALIPAY_DEMO_0001"
}
```

响应体：

```json
{
  "paymentId": 93001,
  "paymentNo": "PAY_DEMO_0001",
  "orderId": 91001,
  "paymentStatusCode": "success",
  "orderStatusCode": "paid",
  "processed": true
}
```

接口实现细节：

- 回调接口不读取 `X-User-Id`，只校验 `X-Demo-Payment-Signature`。
- 先按 `paymentNo` 查询支付记录，并校验 `orderId`、`paymentMethodCode`、`amount` 与库中记录一致；任一字段不一致直接返回错误。
- `statusCode` 取值固定为 `success`、`failed`、`closed`。
- 若支付记录已是终态，接口按幂等规则返回当前支付和订单状态，不重复执行业务更新。
- 当 `statusCode = success` 时，固定执行支付成功后置处理。
- 当 `statusCode = failed` 时，更新 `payments.status_code = 'failed'`，订单保持 `pending_payment`。
- 当 `statusCode = closed` 时，更新 `payments.status_code = 'closed'`，订单保持 `pending_payment`。

#### 4.7 `GET /api/v1/payments/{paymentId}`
说明：查询单笔支付记录状态。

主要关联表：

- `payments`
- `orders`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `paymentId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "paymentId": 93001,
  "paymentNo": "PAY_DEMO_0001",
  "orderId": 91001,
  "paymentMethodCode": "alipay",
  "amount": 1628.00,
  "statusCode": "success",
  "paidAt": "2025-05-01 10:30:00",
  "createdAt": "2025-05-01 10:15:00"
}
```

接口实现细节：

- 查询条件固定为 `payments.id = paymentId and payments.user_id = currentUserId`。
- 支付记录不存在或不属于当前用户时，接口直接返回错误。
- 返回支付记录当前状态，不在该接口内创建新支付单。

#### 4.8 `POST /api/v1/payments/{paymentId}/close`
说明：关闭未支付的支付单。

主要关联表：

- `payments`
- `orders`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `paymentId`：路径参数，必填

请求体：

```json
{
  "closeReason": "user_cancel"
}
```

响应体：

```json
{
  "paymentId": 93001,
  "paymentNo": "PAY_DEMO_0001",
  "orderId": 91001,
  "statusCode": "closed",
  "updatedAt": "2025-05-01 10:25:00"
}
```

接口实现细节：

- 查询条件固定为 `payments.id = paymentId and payments.user_id = currentUserId`。
- 只允许关闭 `payments.status_code = 'pending'` 的支付记录。
- 关闭支付单时固定更新 `payments.status_code = 'closed'` 和 `payments.updated_at`。
- 关闭支付单不直接取消订单；订单仍保持 `pending_payment`，用户重新发起支付时创建新的支付单。
- 若支付记录已是 `success`、`failed` 或 `closed`，接口按幂等规则返回当前状态，不重复更新。

#### 4.9 后台任务 `close_expired_pending_orders`
说明：关闭超时未支付订单，并释放已占用资源。

主要关联表：

- `orders`
- `order_items`
- `payments`
- `user_coupons`
- `member_accounts`
- `order_point_usages`
- `member_point_ledger`
- 商品库存表

触发方式：

- 标准实现应由后台定时任务固定周期执行。
- 当前 app 仅实现任务函数 `close_expired_pending_orders()`，尚未接入实际调度器。

处理规则：

- 扫描条件固定为 `orders.status_code = 'pending_payment'`，且订单下最新一笔 `pending` 支付单创建时间超过支付有效期。
- 关闭订单下所有 `pending` 支付记录，更新为 `payments.status_code = 'closed'`。
- 更新订单为 `orders.status_code = 'cancelled'`，写入 `cancel_reason = 'payment_timeout'` 和 `finalized_at`。
- 更新订单明细为 `order_items.status_code = 'cancelled'`，写入 `cancelled_at`。
- 释放已占用库存。
- 将已核销优惠券恢复为 `user_coupons.status_code = 'available'`。
- 返还已使用积分，并删除或冲正本次订单关联的积分抵扣流水。
- 任务按订单维度幂等执行，重复扫描已取消订单不产生二次回退。

#### 4.10 支付成功后置处理
说明：支付成功后统一更新订单、订单明细、积分和会员成长值。

主要关联表：

- `payments`
- `orders`
- `order_items`
- `member_accounts`
- `member_point_ledger`

触发方式：

- `POST /api/v1/payments/callback` 收到 `statusCode = success` 后触发。

处理规则：

- 更新支付记录为 `payments.status_code = 'success'`，写入 `payments.paid_at`。
- 更新订单为 `orders.status_code = 'paid'`，写入 `orders.paid_at`、`orders.paid_amount`、`orders.settlement_amount`。
- 更新订单明细为 `order_items.status_code = 'paid'`，写入 `order_items.paid_at`。
- 机票、火车票、汽车票在出票完成后再由 `paid` 流转为 `ticketed`。
- 按实付金额生成积分奖励流水，写入 `member_point_ledger.ledger_type_code = 'order_earn'`。
- 更新会员账户 `member_accounts.points_balance`、`member_accounts.total_points` 和 `member_accounts.growth_value`。
- 支付成功后置处理按 `paymentId` 幂等执行，重复触发不重复发放积分、不重复更新金额。

#### 4.11 `GET /api/v1/orders/{orderId}/payments`
说明：查询订单支付记录。

主要关联表：

- `payments`
- `orders`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `orderId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "paymentId": 93001,
      "paymentNo": "PAY_DEMO_0001",
      "paymentMethodCode": "alipay",
      "amount": 1628.00,
      "statusCode": "success",
      "paidAt": "2025-05-01 10:30:00"
    }
  ]
}
```

接口实现细节：

- 先按 `orderId` 查询订单，校验订单属于当前用户；不存在则直接返回错误。
- 查询条件固定为 `payments.order_id = orderId and payments.user_id = currentUserId`。
- 列表按 `created_at desc, id desc` 倒序返回。

### 5. 售后与退款
面向用户发起退款、跟踪退款状态、查看退款打款结果。

#### 5.1 `POST /api/v1/orders/{orderId}/items/{itemId}/refund-requests`
说明：对指定订单明细发起退款申请。

主要关联表：

- `refund_requests`
- `orders`
- `order_items`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `orderId`：路径参数，必填
- `itemId`：路径参数，必填

请求体：

```json
{
  "requestedAmount": 299.00,
  "reason": "行程取消"
}
```

响应体：

```json
{
  "refundRequestId": 94001,
  "refundRequestNo": "RR_DEMO_0001",
  "orderId": 91001,
  "orderItemId": 92001,
  "requestedAmount": 299.00,
  "statusCode": "pending",
  "requestedAt": "2025-05-01 15:00:00"
}
```

接口实现细节：

- 退款发起对象固定为 `order_item_id`，不支持整单直接退款。
- 先按 `orderId`、`itemId` 查询订单和订单明细，校验订单属于当前用户且明细属于该订单；校验失败直接返回错误。
- 只允许对已支付、未完成全额退款的订单明细发起退款申请。
- `requestedAmount` 不得大于该明细剩余可退金额；超额申请直接返回错误。
- 同一订单明细存在进行中的退款申请时，不允许重复发起退款。
- 创建退款申请时固定写入待处理状态 `pending`。

#### 5.2 `GET /api/v1/refund-requests`
说明：查询当前用户退款申请列表。

主要关联表：

- `refund_requests`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `statusCode`：可选，退款申请状态；取值 `pending`、`approved`、`rejected`、`success`
- `requestedFrom`：可选，开始时间，筛选 `requested_at >= requestedFrom` 的退款申请
- `requestedTo`：可选，结束时间，筛选 `requested_at <= requestedTo` 的退款申请
- `pageNo`：可选，默认 `1`
- `pageSize`：可选，默认 `20`

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "refundRequestId": 94001,
      "refundRequestNo": "RR_DEMO_0001",
      "orderId": 91001,
      "orderItemId": 92001,
      "requestedAmount": 299.00,
      "approvedAmount": null,
      "statusCode": "pending",
      "requestedAt": "2025-05-01 15:00:00",
      "processedAt": null
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

接口实现细节：

- 查询条件固定为 `refund_requests.user_id = currentUserId`。
- 若传入 `statusCode`，筛选条件固定为 `refund_requests.status_code = statusCode`。
- 列表按 `requested_at desc, id desc` 倒序返回。

#### 5.3 `GET /api/v1/refund-requests/{refundRequestId}`
说明：查询退款申请详情和退款打款结果。

主要关联表：

- `refund_requests`
- `refund_records`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `refundRequestId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "refundRequestId": 94001,
  "refundRequestNo": "RR_DEMO_0001",
  "orderId": 91001,
  "orderItemId": 92001,
  "requestedAmount": 299.00,
  "approvedAmount": 299.00,
  "statusCode": "approved",
  "requestedAt": "2025-05-01 15:00:00",
  "processedAt": "2025-05-01 16:00:00",
  "refundRecord": {
    "refundId": 95001,
    "refundNo": "RF_DEMO_0001",
    "amount": 299.00,
    "statusCode": "success",
    "processedAt": "2025-05-01 16:10:00"
  }
}
```

接口实现细节：

- 查询条件固定为 `refund_requests.id = refundRequestId and refund_requests.user_id = currentUserId`。
- 退款详情固定同时返回 `requestedAmount`、`approvedAmount` 和退款记录中的实际退款金额。
- 若退款申请不存在或不属于当前用户，接口直接返回错误。

#### 5.4 `GET /api/v1/orders/{orderId}/refund-records`
说明：查询指定订单下的退款记录列表。

主要关联表：

- `refund_records`
- `orders`

请求头：

- `X-User-Id: <user_id>`：演示环境用户标识，直接使用 `users.id`

请求参数：

- `orderId`：路径参数，必填

请求体：

- 无

响应体：

```json
{
  "list": [
    {
      "refundId": 95001,
      "refundNo": "RF_DEMO_0001",
      "refundRequestId": 94001,
      "orderItemId": 92001,
      "amount": 299.00,
      "statusCode": "success",
      "processedAt": "2025-05-01 16:10:00"
    }
  ]
}
```

接口实现细节：

- 先按 `orderId` 查询订单，校验订单属于当前用户；不存在则直接返回错误。
- 查询条件固定为 `refund_records.order_id = orderId and refund_records.user_id = currentUserId`。
- 列表按 `created_at desc, id desc` 倒序返回。
