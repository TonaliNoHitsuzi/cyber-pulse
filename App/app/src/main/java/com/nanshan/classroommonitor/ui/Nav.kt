package com.nanshan.classroommonitor.ui

import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf

sealed class Screen {
    data object Home : Screen()
    data object NewSession : Screen()
    data class Connect(val sessionId: Long) : Screen()
    data class Measure(val sessionId: Long) : Screen()
    data class SessionDetail(val sessionId: Long) : Screen()
    data object Dev : Screen()
}

class Navigator {
    val stack = mutableStateListOf<Screen>(Screen.Home)
    val current: Screen get() = stack.last()
    val canPop = mutableStateOf(false)

    fun push(s: Screen) {
        stack.add(s)
        canPop.value = stack.size > 1
    }

    fun pop() {
        if (stack.size > 1) {
            stack.removeAt(stack.size - 1)
            canPop.value = stack.size > 1
        }
    }

    fun popToHome() {
        stack.clear()
        stack.add(Screen.Home)
        canPop.value = false
    }
}
