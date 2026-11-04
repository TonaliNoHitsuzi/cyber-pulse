package com.nanshan.classroommonitor.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

class Repository(context: Context) {
    private val db = AppDatabase.get(context)
    private val sDao = db.sessionDao()
    private val pDao = db.sampleDao()
    private val wDao = db.waveDao()
    private val uiDao = db.uiFrameDao()
    private val imuDao = db.imuDao()

    fun observeSessions(): Flow<List<SessionEntity>> = sDao.observeAll()
    suspend fun session(id: Long): SessionEntity? = sDao.getById(id)
    suspend fun allSessions(): List<SessionEntity> = sDao.listAll()
    suspend fun recentProfiles(): List<ProfileRow> = sDao.recentProfiles()
    suspend fun createSession(s: SessionEntity): Long = sDao.insert(s)
    suspend fun markStarted(id: Long) = sDao.markStarted(id, startedAt = System.currentTimeMillis())
    suspend fun setStatus(id: Long, st: SessionStatus) = sDao.setStatus(id, st.name)
    suspend fun markEnded(id: Long) = sDao.markEnded(id, endedAt = System.currentTimeMillis())
    suspend fun deleteSession(id: Long) = sDao.deleteWithSamples(id)
    /** 启动时把上次未正常结束的会话收尾（单线流程：不允许挂着） */
    suspend fun closeOrphanSessions() =
        sDao.closeOrphans(SessionStatus.DONE.name, System.currentTimeMillis())

    suspend fun insertSamples(list: List<SampleEntity>) = pDao.insertAll(list)
    suspend fun insertWaveChunks(list: List<WaveChunkEntity>) = wDao.insertAll(list)
    suspend fun waveChunksOf(id: Long): List<WaveChunkEntity> = wDao.ofSession(id)
    suspend fun waveChunkCount(id: Long): Int = wDao.countOf(id)
    suspend fun insertUiFrames(list: List<UiFrameEntity>) = uiDao.insertAll(list)
    suspend fun uiFramesOf(id: Long): List<UiFrameEntity> = uiDao.ofSession(id)
    suspend fun insertImuChunks(list: List<ImuChunkEntity>) = imuDao.insertAll(list)
    suspend fun imuChunksOf(id: Long): List<ImuChunkEntity> = imuDao.ofSession(id)
    suspend fun samplesOf(id: Long): List<SampleEntity> = pDao.ofSession(id)
    suspend fun countOf(id: Long): Int = pDao.countOf(id)
    suspend fun statsOf(id: Long): List<ChannelStat> = pDao.statsOf(id)
    /** 通道活跃度检测（开发者注入/连接检查用）：近 windowMs 内该通道样本数 */
    suspend fun countSince(id: Long, ch: ChannelType, since: Long) =
        pDao.countSince(id, ch.name, since)

    companion object {
        @Volatile private var inst: Repository? = null
        fun get(context: Context): Repository =
            inst ?: synchronized(this) { Repository(context).also { inst = it } }

        fun iso(ms: Long): String {
            val f = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
            f.timeZone = TimeZone.getTimeZone("UTC")
            return f.format(Date(ms))
        }

        fun local(ms: Long): String {
            val f = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
            return f.format(Date(ms))
        }
    }
}
