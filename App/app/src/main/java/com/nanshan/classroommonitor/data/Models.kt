package com.nanshan.classroommonitor.data

/**
 * 采集通道全集。source 决定数据从哪来：
 * - PHONE：手机自带传感器（原型期即真实可用）
 * - WATCH：手表数据，走华为通道适配层（hi 包）；原型期仅靠开发者注入/模拟发生器
 * - RESEARCH_ONLY：需 Research 平台资源码（如 continuousheartrate / PPG 原始波形）
 */
enum class ChannelSource(val label: String) {
    WATCH("手表通道（主）"),
    RESEARCH_ONLY("Research专属·需资源码"),
    PHONE("手机传感器（调试用）")
}

enum class ChannelType(val label: String, val unit: String, val source: ChannelSource) {
    HEART_RATE("脉搏", "bpm", ChannelSource.PHONE),
    SPO2("血氧", "%", ChannelSource.WATCH),
    SKIN_TEMP("皮温", "℃", ChannelSource.WATCH),
    RRI_HRV("RRI/HRV", "ms", ChannelSource.RESEARCH_ONLY),
    PPG("PPG原始波形", "au", ChannelSource.RESEARCH_ONLY),
    ACCELEROMETER("加速度", "m/s²", ChannelSource.PHONE),
    GYROSCOPE("陀螺仪", "rad/s", ChannelSource.PHONE),
    STEP_COUNT("计步", "步", ChannelSource.PHONE);

    companion object {
        fun from(name: String?): ChannelType? = entries.firstOrNull { it.name == name }
    }
}

enum class SessionStatus(val label: String) {
    CREATED("已创建"),
    RECORDING("采集中"),
    PAUSED("已暂停"),
    DONE("已结束");
}

/** 样本来源标记（分析时区分真机/注入/模拟） */
object SampleSource {
    const val PHONE_SENSOR = "PHONE_SENSOR"
    const val PIEZO = "PIEZO_BLE"
    const val DEV_INJECT = "DEV_INJECT"
    const val MOCK_GEN = "MOCK_GEN"
}
