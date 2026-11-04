package com.nanshan.classroommonitor.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "sessions")
data class SessionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val classId: String,
    val studentId: String,
    val studentName: String,
    val note: String = "",
    /** 逗号分隔的 ChannelType.name 列表 */
    val channels: String,
    val status: String = SessionStatus.CREATED.name,
    val createdAt: Long,
    val startedAt: Long? = null,
    val endedAt: Long? = null,
    val deviceLabel: String = "",
    val appVersion: String = "",
    /* 测量标注（配置 JSON 驱动，字段固定落库以便统计） */
    val gender: String = "",
    val hand: String = "左手",
    val finger: String = "拇指",
    val exercise: String = "静坐",
    val height: Double? = null,
    val weight: Double? = null,
    val weather: String = "",
    val temperature: Double? = null,
    val humidity: Double? = null,
    /** 动态表单其余字段的 JSON 扩展位 */
    val extraJson: String? = null
)

@Entity(tableName = "samples")
data class SampleEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val channel: String,
    val tsMillis: Long,
    val value: Double,
    /** 多轴等复杂数据的 JSON 扩展位 */
    val extraJson: String? = null,
    val quality: String = "OK",
    val sourceTag: String
)

data class ProfileRow(
    val name: String,
    val sid: String?,
    val gender: String?,
    val height: Double?,
    val weight: Double?,
    val lastTs: Long
)

@Dao
interface SessionDao {
    @Insert
    suspend fun insert(s: SessionEntity): Long

    @Query("UPDATE sessions SET status=:status, startedAt=:startedAt WHERE id=:id")
    suspend fun markStarted(id: Long, status: String = SessionStatus.RECORDING.name, startedAt: Long)

    @Query("UPDATE sessions SET status=:status WHERE id=:id")
    suspend fun setStatus(id: Long, status: String)

    @Query("UPDATE sessions SET status=:status, endedAt=:endedAt WHERE id=:id")
    suspend fun markEnded(id: Long, status: String = SessionStatus.DONE.name, endedAt: Long)

    @Query("SELECT * FROM sessions ORDER BY id DESC")
    fun observeAll(): Flow<List<SessionEntity>>

    @Query("SELECT * FROM sessions ORDER BY id DESC")
    suspend fun listAll(): List<SessionEntity>

    @Query("SELECT * FROM sessions WHERE id=:id")
    suspend fun getById(id: Long): SessionEntity?

    @Query("SELECT studentName AS name, studentId AS sid, gender, height, weight, MAX(startedAt) AS lastTs " +
           "FROM sessions WHERE studentName != '' AND studentName NOT LIKE '%Cal%' " +
           "GROUP BY studentName ORDER BY lastTs DESC LIMIT 12")
    suspend fun recentProfiles(): List<ProfileRow>

    @Query("UPDATE sessions SET status=:done, endedAt=:now WHERE status IN ('RECORDING','PAUSED')")
    suspend fun closeOrphans(done: String, now: Long)

    @Query("DELETE FROM sessions WHERE id=:id")
    suspend fun delete(id: Long)

    @Query("DELETE FROM samples WHERE sessionId=:id")
    suspend fun deleteSamplesOf(id: Long)

    @Transaction
    suspend fun deleteWithSamples(id: Long) {
        deleteSamplesOf(id)
        delete(id)
    }
}

@Dao
interface SampleDao {
    @Insert
    suspend fun insertAll(list: List<SampleEntity>)

    @Query("SELECT * FROM samples WHERE sessionId=:sessionId ORDER BY tsMillis ASC")
    suspend fun ofSession(sessionId: Long): List<SampleEntity>

    @Query("SELECT COUNT(*) FROM samples WHERE sessionId=:sessionId")
    suspend fun countOf(sessionId: Long): Int

    @Query("SELECT channel, COUNT(*) as n, MIN(value) as vmin, MAX(value) as vmax FROM samples WHERE sessionId=:sessionId GROUP BY channel")
    suspend fun statsOf(sessionId: Long): List<ChannelStat>

    @Query("SELECT COUNT(*) FROM samples WHERE sessionId=:sessionId AND channel=:channel AND tsMillis>=:since")
    suspend fun countSince(sessionId: Long, channel: String, since: Long): Int
}

data class ChannelStat(val channel: String, val n: Int, val vmin: Double, val vmax: Double)

/** 每 500ms 的实时帧（复盘"当时屏幕显示什么"） */
@Entity(tableName = "ui_frames", indices = [androidx.room.Index(value = ["sessionId", "ts"], unique = true)])
data class UiFrameEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val ts: Long,
    val bpm: Int, val bpm2: Int,
    val sc: Float,
    val state: String,
    val p95: Int, val p50: Int,
    val q: Int
)

/** 手机 IMU 块（50Hz，每秒一块：[dt_ms(2B) aMag×100(2B) gMag×100(2B)] × n） */
@Entity(tableName = "imu_chunks")
data class ImuChunkEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val startTs: Long,
    val n: Int,
    val data: ByteArray
)

@Dao
interface UiFrameDao {
    @Insert(onConflict = androidx.room.OnConflictStrategy.IGNORE)
    suspend fun insertAll(list: List<UiFrameEntity>)
    @Query("SELECT * FROM ui_frames WHERE sessionId=:id ORDER BY ts ASC")
    suspend fun ofSession(id: Long): List<UiFrameEntity>
}

@Dao
interface ImuDao {
    @Insert
    suspend fun insertAll(list: List<ImuChunkEntity>)
    @Query("SELECT * FROM imu_chunks WHERE sessionId=:id ORDER BY startTs ASC")
    suspend fun ofSession(id: Long): List<ImuChunkEntity>
}

@Entity(
    tableName = "wave_chunks",
    indices = [androidx.room.Index(value = ["sessionId", "startTs"], unique = true)]
)
data class WaveChunkEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val startTs: Long,
    val count: Int,
    val data: ByteArray
)

@Dao
interface WaveDao {
    @Insert(onConflict = androidx.room.OnConflictStrategy.IGNORE)
    suspend fun insertAll(list: List<WaveChunkEntity>)

    @Query("SELECT * FROM wave_chunks WHERE sessionId=:sessionId ORDER BY startTs ASC")
    suspend fun ofSession(sessionId: Long): List<WaveChunkEntity>

    @Query("SELECT COUNT(*) FROM wave_chunks WHERE sessionId=:sessionId")
    suspend fun countOf(sessionId: Long): Int
}

@Database(entities = [SessionEntity::class, SampleEntity::class, WaveChunkEntity::class, UiFrameEntity::class, ImuChunkEntity::class], version = 7, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun sessionDao(): SessionDao
    abstract fun sampleDao(): SampleDao
    abstract fun waveDao(): WaveDao
    abstract fun uiFrameDao(): UiFrameDao
    abstract fun imuDao(): ImuDao

    companion object {
        @Volatile private var inst: AppDatabase? = null
        fun get(context: Context): AppDatabase =
            inst ?: synchronized(this) {
                inst ?: Room.databaseBuilder(
                    context.applicationContext, AppDatabase::class.java, "classroom_monitor.db"
                ).fallbackToDestructiveMigration().build().also { inst = it }
            }
    }
}
