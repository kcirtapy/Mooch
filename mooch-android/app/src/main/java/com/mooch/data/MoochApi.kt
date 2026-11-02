package com.mooch.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.util.concurrent.TimeUnit

sealed interface FetchResult {
    data class Success(val feed: Feed, val fromCache: Boolean = false) : FetchResult
    data class Failure(val message: String, val stale: Feed? = null) : FetchResult
}

private val json = Json {
    ignoreUnknownKeys = true
    coerceInputValues = true
}

class MoochApi {
    private val client = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    /** Returns the raw JSON body, or throws with a message worth showing a human. */
    fun fetchRaw(settings: Settings): String {
        val url = settings.feedUrl() ?: throw IOException("No server address set")
        val request = Request.Builder()
            .url(url)
            .apply {
                if (settings.token.isNotBlank()) {
                    header("Authorization", "Bearer ${settings.token}")
                }
            }
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (response.code == 401) {
                throw IOException("Server rejected the token. Check Settings.")
            }
            if (!response.isSuccessful) {
                throw IOException("Server returned ${response.code}")
            }
            if (body.isBlank()) throw IOException("Server returned an empty response")
            return body
        }
    }
}

class EventRepository(context: Context) {
    private val api = MoochApi()
    private val settingsRepo = SettingsRepository(context.applicationContext)

    val settings = settingsRepo.settings

    suspend fun refresh(): FetchResult = withContext(Dispatchers.IO) {
        val current = settingsRepo.current()
        if (!current.isConfigured) {
            return@withContext FetchResult.Failure("No server address set yet")
        }

        try {
            val raw = api.fetchRaw(current)
            val feed = json.decodeFromString<Feed>(raw)
            settingsRepo.cacheFeed(raw)
            FetchResult.Success(feed.filtered(current.minConfidence))
        } catch (e: Exception) {
            val stale = loadCache(current.minConfidence)
            FetchResult.Failure(friendly(e), stale)
        }
    }

    /** Last good feed, so the list isn't blank when the laptop is asleep. */
    suspend fun cached(): FetchResult? = withContext(Dispatchers.IO) {
        val current = settingsRepo.current()
        loadCache(current.minConfidence)?.let { FetchResult.Success(it, fromCache = true) }
    }

    private suspend fun loadCache(minConfidence: Float): Feed? =
        settingsRepo.cachedFeed()?.let {
            runCatching { json.decodeFromString<Feed>(it).filtered(minConfidence) }.getOrNull()
        }

    /** Used by the sync worker: fetch and report which events are newly seen. */
    suspend fun refreshForSync(): Pair<Feed, Set<String>>? = withContext(Dispatchers.IO) {
        val current = settingsRepo.current()
        if (!current.isConfigured) return@withContext null

        val feed = try {
            val raw = api.fetchRaw(current)
            json.decodeFromString<Feed>(raw).also { settingsRepo.cacheFeed(raw) }
        } catch (e: Exception) {
            return@withContext null
        }

        val relevant = feed.filtered(current.minConfidence)
        val already = settingsRepo.notifiedIds()
        val fresh = relevant.events
            .filter { !it.isPast() && it.id !in already }
            .map { it.id }
            .toSet()

        relevant to fresh
    }

    suspend fun markNotified(ids: Set<String>) = settingsRepo.markNotified(ids)
}

private fun Feed.filtered(minConfidence: Float): Feed =
    if (minConfidence <= 0f) this
    else copy(events = events.filter { it.confidence >= minConfidence })

private fun friendly(e: Exception): String = when {
    e is IOException && e.message?.contains("token", true) == true -> e.message!!
    e is java.net.SocketTimeoutException -> "Laptop didn't answer in time. Is `mooch serve` running?"
    e is java.net.ConnectException -> "Can't reach the laptop. Same wifi? Server running?"
    e is java.net.UnknownHostException -> "Can't resolve that address. Check the URL in Settings."
    e is IOException -> e.message ?: "Network error"
    else -> "Couldn't read the feed: ${e.message ?: e::class.simpleName}"
}
