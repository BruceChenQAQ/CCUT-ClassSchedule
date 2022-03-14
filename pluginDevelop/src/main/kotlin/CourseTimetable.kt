package org.brucechen

import com.google.gson.Gson
import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import net.mamoe.mirai.Bot
import net.mamoe.mirai.console.command.CommandManager.INSTANCE.register
import net.mamoe.mirai.console.command.CommandManager.INSTANCE.unregister
import net.mamoe.mirai.console.command.CommandSender
import net.mamoe.mirai.console.command.SimpleCommand
import net.mamoe.mirai.console.data.AutoSavePluginConfig
import net.mamoe.mirai.console.data.value
import net.mamoe.mirai.console.plugin.jvm.JvmPluginDescription
import net.mamoe.mirai.console.plugin.jvm.KotlinPlugin
import net.mamoe.mirai.event.GlobalEventChannel
import net.mamoe.mirai.event.events.FriendMessageEvent
import net.mamoe.mirai.event.events.NewFriendRequestEvent
import net.mamoe.mirai.message.data.content
import net.mamoe.mirai.utils.info
import org.brucechen.Command_unbindkcb.handle
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.sql.Connection
import java.sql.DriverManager
import java.text.ParseException
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit


const val helpMsg = """发送"帮助"可再次收取帮助信息

##### 网页服务 #####

 签到：auto-sign.brucec.cn
 课表：kcb.brucec.cn


##### 交互指令 #####

绑定教务系统(课程表)账号:
 /bindkcb 学号 教务系统密码
 /bindkcb 20991111 123456

解除绑定教务系统账号:
 /unbindkcb 学号
 /unbindkcb 20991111

每日课程表推送开关:
 /setkcb push 学号 on/off
 /setkcb push 20991111 on

周末无课程时课程表推送开关:
 /setkcb wkpush 学号 on/off
 /setkcb wkpush 20991111 on

获取完整课程表网页链接:
 /mykcb
 
快速查课表指令:
  发送"快捷指令"查询"""

const val queryShortStr = """发送相似指令均可查询课表

明天课表
今日课表
查看昨天课程
查询后天课
大后天的课程表
3月8日课表
3.8
4.55课表
查询3-8课程表
22-3/8课程
2022.3.8课表
上周四课表
本周一课表
周二课
下周三课程表
下下周五课程
查询下下下周二课程表

查询完整课表请发送/mykcb"""

val startOfTeachingWeek: Date = SimpleDateFormat("yyyy-MM-dd").parse("2022-2-28")!!

var CourseTimetableserver: CourseWebSocketServer? = null
var CourseTimetableDBConn: Connection? = null

var gson = Gson()

object CourseTimetable : KotlinPlugin(
    JvmPluginDescription(
        id = "org.brucechen.course_timetable",
        version = "1.0",
    )
) {
    override fun onEnable() {
        logger.info { "插件加载中" }

        /* 配置数据加载 */
        // MyData.reload()
        CourseTimetableConfig.reload()

        /* WebSocket初始化 */
        CourseTimetableserver = CourseWebSocketServer(CourseTimetableConfig.WebSocketPort)
        CourseTimetableserver!!.start()

        /* 数据库连接初始化 */
        Class.forName("org.sqlite.JDBC")
        CourseTimetableDBConn = DriverManager.getConnection("jdbc:sqlite:" + CourseTimetableConfig.DatabasePos)
        CourseTimetableDBConn!!.autoCommit = true

        /* 定时任务 */
        val calendar = Calendar.getInstance()
        calendar.add(Calendar.DAY_OF_YEAR, 1)
        val nextExecuteDate = SimpleDateFormat("yyyy-MM-dd").format(calendar.time) + " 5:30:00"
//        val nextExecuteDate = SimpleDateFormat("yyyy-MM-dd").format(calendar.time) + " 14:14:00"
        logger.info { "下次执行时间: $nextExecuteDate" }
        val startDate = SimpleDateFormat("yyyy-MM-dd hh:mm:ss").parse(nextExecuteDate)
//        Timer().schedule(TaskPushSchedule(), startDate, 60L * 1000L)
        Timer().schedule(TaskPushSchedule(), startDate, 24L * 3600L * 1000L)
        logger.info { "插件加载成功" }

        /* 好友消息交互 */
        GlobalEventChannel.subscribeAlways<FriendMessageEvent> { event ->
            val message = event.message.content.replace("\\s+".toRegex(),"")
            if ("你好[呀|啊]*[二|2]*号*".toRegex().matches(message) || "[二|2]*号*你好[呀|啊]*".toRegex().matches(message)) {
                subject.sendMessage("你好呀qwq")
            } else if ("晚上*好[二|2]*号*[呀|啊]*".toRegex().matches(message) || "[二|2]*号*晚上*好[呀|啊]*".toRegex().matches(message)) {
                subject.sendMessage("晚上好qwq")
            } else if ("晚安[二|2]*号*[呀|啊]*".toRegex().matches(message) || "[二|2]*号*晚安[呀|啊]*".toRegex().matches(message)) {
                subject.sendMessage("晚安~")
            } else if ("早上*好[二|2]*号*[呀|啊]*".toRegex().matches(message) || "[二|2]*号*早上*好[呀|啊]*".toRegex().matches(message)) {
                subject.sendMessage("早上好qwq")
            } else if ("早安[二|2]*号*[呀|啊]*".toRegex().matches(message) || "[二|2]*号*早安[呀|啊]*".toRegex().matches(message)) {
                subject.sendMessage("早安~")
            } else if (message == "帮助" || message == "help" || message == "?" || message == "？" || message == "查看帮助" || message == "查看帮助信息" || message == "查询帮助信息") {
                subject.sendMessage(helpMsg)
            } else if (message == "快捷指令" || message == "快捷命令" || message == "快捷查询" || message == "快捷" || message == "快速查询" || message == "快速命令") {
                subject.sendMessage(queryShortStr)
            } else {
                val chn2int = mapOf(
                    "一" to 1,
                    "二" to 2,
                    "三" to 3,
                    "四" to 4,
                    "五" to 5,
                    "六" to 6,
                    "七" to 7,
                    "日" to 7,
                    "天" to 7,
                    "1" to 1,
                    "2" to 2,
                    "3" to 3,
                    "4" to 4,
                    "5" to 5,
                    "6" to 6,
                    "7" to 7
                )
                val dateFormat = SimpleDateFormat("yyyy-MM-dd")
                val calendarNow = Calendar.getInstance()
                if ("查*[询|找|看]*明[天|日]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    calendarNow.add(Calendar.DAY_OF_YEAR, 1)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*今[天|日]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*昨[天|日]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    calendarNow.add(Calendar.DAY_OF_YEAR, -1)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*后[天|日]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    calendarNow.add(Calendar.DAY_OF_YEAR, 2)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*明[天|日]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    calendarNow.add(Calendar.DAY_OF_YEAR, 3)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*上周[一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    val nowDayOfWeek: Int = getDayOfWeek(calendarNow.time)
                    val found = "([一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7])".toRegex().findAll(message)
                    val needDayofweek:Int = chn2int[found.elementAt(0).value]!!
                    calendarNow.add(Calendar.DAY_OF_YEAR, -7 + needDayofweek - nowDayOfWeek)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*[本|这|同|该]*周[一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    val nowDayOfWeek: Int = getDayOfWeek(calendarNow.time)
                    val found = "([一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7])".toRegex().findAll(message)
                    val needDayofweek:Int = chn2int[found.elementAt(0).value]!!
                    calendarNow.add(Calendar.DAY_OF_YEAR, needDayofweek - nowDayOfWeek)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*下周[一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    val nowDayOfWeek: Int = getDayOfWeek(calendarNow.time)
                    val found = "([一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7])".toRegex().findAll(message)
                    val needDayofweek:Int = chn2int[found.elementAt(0).value]!!
                    calendarNow.add(Calendar.DAY_OF_YEAR, 7 + needDayofweek - nowDayOfWeek)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*下下周[一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    val nowDayOfWeek: Int = getDayOfWeek(calendarNow.time)
                    val found = "([一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7])".toRegex().findAll(message)
                    val needDayofweek:Int = chn2int[found.elementAt(0).value]!!
                    calendarNow.add(Calendar.DAY_OF_YEAR, 14 + needDayofweek - nowDayOfWeek)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*下下下周[一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7]的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    val nowDayOfWeek: Int = getDayOfWeek(calendarNow.time)
                    val found = "([一|二|三|四|五|六|七|日|天|1|2|3|4|5|6|7])".toRegex().findAll(message)
                    val needDayofweek:Int = chn2int[found.elementAt(0).value]!!
                    calendarNow.add(Calendar.DAY_OF_YEAR, 21 + needDayofweek - nowDayOfWeek)
                    handleMessageQuery(event, dateFormat.parse(dateFormat.format(calendarNow.time)))
                } else if ("查*[询|找|看]*(\\d{2,4})*[年|.|。|\\-|\\/|、]*(\\d{1,2})[月|.|。|\\-|\\/|、](\\d{1,2})[日|号]*的*课*程*[表|本]*[有|是]*[什么|那|哪]*些*[啊|呀|呢]*".toRegex().matches(message)) {
                    val found = "\\d+".toRegex().findAll(message)
                    val foundLen = found.count()
                    if (foundLen == 2 || (foundLen == 3 || found.elementAt(0).value.count() != 3)) {
                        val year: Int
                        val month: Int
                        val day: Int
                        if (foundLen == 2) {
                            year = calendarNow.get(Calendar.YEAR)
                            month = found.elementAt(0).value.toInt()
                            day = found.elementAt(1).value.toInt()
                        } else {
                            year = if (found.elementAt(0).value.count() == 2)
                                (calendarNow.get(Calendar.YEAR) / 100) * 100 + found.elementAt(0).value.toInt()
                            else
                                found.elementAt(0).value.toInt()
                            month = found.elementAt(1).value.toInt()
                            day = found.elementAt(2).value.toInt()
                        }
                        try {
                            val res = dateFormat.parse("$year-$month-$day")
                            handleMessageQuery(event, res)
                        } catch (_: ParseException) {
                        }

                    }
                }
            }
        }

        /* 自动加好友 */
        GlobalEventChannel.subscribeAlways<NewFriendRequestEvent> { event ->
            val QQ = event.fromId
            try {
                event.accept()
            } catch (e: Exception) {
                CourseTimetable.logger.warning(e)
            }
            delay(500)
            val friend = Bot.getInstance(2895727556).getFriend(QQ)
            friend?.sendMessage(helpMsg)
        }

        /* 注册指令 */
        Command_bindkcb.register()
        Command_unbindkcb.register()
        Command_setkcb.register()
        Command_mykcb.register()
    }

    override fun onDisable() {
        CourseTimetableDBConn?.close()
        CourseTimetableserver?.stop()

        /* 取消注册指令 */
        Command_bindkcb.unregister()
        Command_unbindkcb.unregister()
        Command_setkcb.unregister()
        Command_mykcb.unregister()
    }
}

fun getDayOfWeek(dt: Date): Int {
    val weekDays = arrayOf(7, 1, 2, 3, 4, 5, 6)
    val cal = Calendar.getInstance()
    cal.time = dt
    var w = cal[Calendar.DAY_OF_WEEK] - 1
    if (w < 0) {
        w = 0
    }
    return weekDays[w]
}

data class CourseInfo(
    val name: String,
    val teacher: String,
    val weekStr: String,
    val week: List<Int>,
    val place: String
)

data class CourseOfDay(
    val class1: List<CourseInfo>,
    val class2: List<CourseInfo>,
    val class3: List<CourseInfo>,
    val class4: List<CourseInfo>,
    val class5: List<CourseInfo>
) {
    operator fun get(i: Int): List<CourseInfo> {
        return when(i) {
            1 -> class1
            2 -> class2
            3 -> class3
            4 -> class4
            5 -> class5
            else -> class1
        }
    }
}

data class CourseNote(
    val noteStr: String,
    val noteClass: List<CourseInfo>
)

data class CourseOfWeek(
    val mon: CourseOfDay,
    val tue: CourseOfDay,
    val wed: CourseOfDay,
    val thu: CourseOfDay,
    val fri: CourseOfDay,
    val sat: CourseOfDay,
    val sun: CourseOfDay,
    val note: CourseNote?
) {
    operator fun get(i: Int): CourseOfDay {
        return when(i) {
            1 -> this.mon
            2 -> this.tue
            3 -> this.wed
            4 -> this.thu
            5 -> this.fri
            6 -> this.sat
            else -> this.sun
        }
    }
}

fun getWeekOfTeaching(now: Date): Int {
    val diffInMillisec: Long = now.time - startOfTeachingWeek.time
    val diffInDays: Long = TimeUnit.MILLISECONDS.toDays(diffInMillisec)
    return if (diffInDays < 0) 1 else 1 + (diffInDays / 7).toInt()
}

suspend fun handleMessageQuery(event: FriendMessageEvent, queryTime: Date) {
    if (queryTime.time < startOfTeachingWeek.time) {
        event.user.sendMessage("查询课程表失败：不在本学期开课时间内")
        return
    }
    val weekOfTeaching = getWeekOfTeaching(queryTime)
    if (weekOfTeaching >= 30) {
        event.user.sendMessage("查询课程表失败：不在本学期开课时间内")
        return
    }
    val QQ = event.user.id
    if (CourseTimetableDBConn == null)
        CourseTimetableDBConn = DriverManager.getConnection("jdbc:sqlite:" + CourseTimetableConfig.DatabasePos)
    CourseTimetable.logger.info { "处理查询课程表" }
    val statement = CourseTimetableDBConn!!.createStatement()
    val statement2 = CourseTimetableDBConn!!.createStatement()
    val userList = statement.executeQuery("SELECT sid, pushOnWeekend FROM bind WHERE QQ = $QQ")
    val bindCountP = statement2.executeQuery("SELECT count(*) FROM bind WHERE QQ = $QQ")
    var bindCount: Int? = null
    if (bindCountP.next())
        bindCount = bindCountP.getInt(1)
    var flagQuerySuccess = false
    try {
        while (userList.next()) {
            val sid: Int = userList.getInt("sid")
            val coursePoint = statement2.executeQuery("SELECT courseData, updateTime FROM courses WHERE sid = $sid")
            if (coursePoint.next()) {
                flagQuerySuccess = true
                val courseData: String? = coursePoint.getString("courseData")
                val updateTime: String? = coursePoint.getString("updateTime")
                if ((courseData == null) || courseData.isEmpty() || (updateTime == null) || updateTime.isEmpty()) {
                    event.user.sendMessage("查询课程表失败：$sid 的课程表还未抓取成功(可能是密码错误或教务系统关闭等原因)。\n" +
                            "\n" +
                            "可以使用如下指令修改密码:\n" +
                            "/bindkcb 学号 新密码")
                    continue
                }
                val courseOfWeek: CourseOfWeek = gson.fromJson(courseData, CourseOfWeek::class.java)
                val todayCourse = getActualCourseOfDay(courseOfWeek, queryTime)
                if (bindCount!! > 1)
                    pushCourseToUser(QQ, todayCourse, updateTime, queryTime, "$sid 的查询结果：\n")
                else
                    pushCourseToUser(QQ, todayCourse, updateTime, queryTime, null)
            }
            delay((300..800).random().toLong())
        }
    } catch (e: Exception) {
        CourseTimetable.logger.error(e)
    } finally {
        statement.close()
        statement2.close()
    }
    if (bindCount!! == 0)
        event.user.sendMessage("查询课程表失败：当前未绑定任何账号，请使用如下指令进行绑定 /bindkcb 学号 教务系统登录密码")
    else if (!flagQuerySuccess)
        event.user.sendMessage("查询课程表失败：当前所绑定账号课程表还未抓取成功(可能是密码错误或教务系统关闭等原因)。\n\n可以使用如下指令修改密码:\n/bindkcb 学号 新密码")
}

fun getActualCourseOfDay(courseOfWeek: CourseOfWeek, queryTime: Date): List<CourseInfo?> {
    val res = mutableListOf<CourseInfo?>()
    val weekOfTeaching = getWeekOfTeaching(queryTime)
    val dayOfWeek = getDayOfWeek(queryTime)
    val courseOfDay: CourseOfDay = courseOfWeek[dayOfWeek]
    for (cidx in 1..5) {
        var flagFind = false
        val courseOfSection = courseOfDay[cidx]
        for (course in courseOfSection) {
            if (course.week.contains(weekOfTeaching)) {
                res.add(course)
                flagFind = true
                break
            }
        }
        if (!flagFind)
            res.add(null)
    }
    return res
}

suspend fun pushCourseToUser(QQ: Long, courses: List<CourseInfo?>, updateTime: String, queryTime: Date?, headString: String?) {
//    val friend = Bot.getInstance(2821579492L).getFriend(QQ) ?: return
    val friend = Bot.getInstance(2895727556).getFriend(QQ) ?: return
    val int2chn = mapOf(
        1 to "一",
        2 to "二",
        3 to "三",
        4 to "四",
        5 to "五",
        6 to "六",
        7 to "日"
    )
    val int2circle = mapOf(
        1 to "①",
        2 to "②",
        3 to "③",
        4 to "④",
        5 to "⑤"
    )
    val myQueryTime = queryTime ?: Date()
    val weekOfTeaching = getWeekOfTeaching(myQueryTime)
    val dayOfWeek = getDayOfWeek(myQueryTime)
    var res: String = headString ?: ""
    res += if (queryTime == null) "今天是" else "查询"
    res += SimpleDateFormat("MM月dd日").format(myQueryTime.time) + "星期" + int2chn[dayOfWeek] + " (第" + weekOfTeaching + "周)\n"
    res += "(数据更新于$updateTime)"
    for (i in 1..5) {
        val course = courses[i - 1]
        res += "\n\n" + int2circle[i] + " "
        res += if (course == null) {
            "空"
        } else {
            course.name + "(" + course.teacher + ")\n　 " + course.place
        }
    }

    friend.sendMessage(res)
}

fun IntRange.random() =
    Random().nextInt((endInclusive + 1) - start) + start

class TaskPushSchedule() : TimerTask() {
    @OptIn(DelicateCoroutinesApi::class)
    override fun run() {
        GlobalScope.launch{
            CourseTimetable.logger.info { "开始推送课程表" }
            val dayOfWeek = getDayOfWeek(Date())
            if (CourseTimetableDBConn == null)
                CourseTimetableDBConn = DriverManager.getConnection("jdbc:sqlite:" + CourseTimetableConfig.DatabasePos)
            val statement = CourseTimetableDBConn!!.createStatement()
            val statement2 = CourseTimetableDBConn!!.createStatement()
            val userList = statement.executeQuery("SELECT sid, QQ, pushOnWeekend FROM bind WHERE pushMorning = 1")
            while (userList.next()) {
                val sid: Int = userList.getInt("sid")
                val QQ: Long = userList.getLong("QQ")
                val bindCountP = statement2.executeQuery("SELECT count(*) FROM bind WHERE QQ = $QQ")
                var bindCount: Int? = null
                if (bindCountP.next())
                    bindCount = bindCountP.getInt(1)
                val coursePoint = statement2.executeQuery("SELECT courseData, updateTime FROM courses WHERE sid = $sid")
                if (coursePoint.next()) {
                    val courseData: String? = coursePoint.getString("courseData")
                    val updateTime: String? = coursePoint.getString("updateTime")
                    if (courseData == null || courseData.isEmpty() || updateTime == null || updateTime.isEmpty()) {
                        Bot.getInstance(2895727556).getFriend(QQ)?.sendMessage("查询课程表失败：$sid 的课程表还未抓取成功(可能是密码错误或教务系统关闭等原因)")
                        continue
                    }
                    val courseOfWeek: CourseOfWeek = gson.fromJson(courseData, CourseOfWeek::class.java)
                    val todayCourse = getActualCourseOfDay(courseOfWeek, Date())
                    if ((!userList.getBoolean("pushOnWeekend")) && (dayOfWeek == 6 || dayOfWeek == 7)) {
                        var flagPush = false
                        for (course in todayCourse) {
                            if (course != null) {
                                flagPush = true
                                break
                            }
                        }
                        if (!flagPush)
                            continue
                    }
                    if (bindCount!! > 1)
                        pushCourseToUser(QQ, todayCourse, updateTime, null, "用户 $sid 的推送:\n")
                    else
                        pushCourseToUser(QQ, todayCourse, updateTime, null, null)
                    delay((800..2000).random().toLong())
                }
            }
            statement.close()
            statement2.close()
        }
    }
}


data class UserInfo(
    val QQ: String,
    val username: String,
    val password: String,
    val type: String
)

fun checkSid(sid: String): Boolean {
    val re = "20\\d{6}".toRegex()
    return re.matchEntire(sid) != null
}

object Command_bindkcb : SimpleCommand(
    CourseTimetable, "bindkcb", "绑定教务系统账号",
    description = "绑定教务系统账号, 用法 /bindkcb 学号 密码"
) {
    @Handler
    suspend fun CommandSender.handle(studentID: String, passwd: String) {
        val sid = studentID.replace("\\s".toRegex(),"")
        if (!checkSid(sid)) {
            sendMessage("绑定教务系统账号失败：学号格式不正确")
            return
        }
        val QQ = this.user!!.id
        val jsonMsg = gson.toJson(UserInfo(QQ = QQ.toString(), username = sid, password = passwd, type = "bind"))
        CourseTimetableserver!!.broadcast(jsonMsg)
    }
}

object Command_unbindkcb : SimpleCommand(
    CourseTimetable, "unbindkcb", "解除绑定教务系统账号",
    description = "解除绑定教务系统账号, 用法 /unbindkcb 学号"
) {
    @Handler
    suspend fun CommandSender.handle(studentID: String) {
        val sid = studentID.replace("\\s".toRegex(),"")
        if (!checkSid(sid)) {
            sendMessage("绑定教务系统账号失败：学号格式不正确")
            return
        }
        val QQ = this.user!!.id
        if (CourseTimetableDBConn == null)
            CourseTimetableDBConn = DriverManager.getConnection("jdbc:sqlite:" + CourseTimetableConfig.DatabasePos)
        val statement = CourseTimetableDBConn!!.createStatement()
        val resultQQ = statement.executeQuery("SELECT 1 FROM bind WHERE sid = $sid and QQ = $QQ")
        if (resultQQ.next()) {
            statement.executeUpdate("DELETE FROM bind WHERE sid = $sid and QQ = $QQ")
            sendMessage("解除绑定教务系统账号成功，已解绑 $sid 。")
        } else {
            sendMessage("解除绑定教务系统账号失败：不存在绑定关系。")
        }
        statement.close()
    }
}

object Command_setkcb : SimpleCommand(
    CourseTimetable, "setkcb", "课程表推送设置",
    description = "每日课程表推送设置, 用法 /setkcb [push/wkpush] 学号 [on/off]"
) {
    @Handler
    suspend fun CommandSender.handle(cmd : String, studentID: String, enabled: String) {
        val sid = studentID.replace("\\s".toRegex(),"")
        if (!checkSid(sid)) {
            sendMessage("绑定教务系统账号失败：学号格式不正确")
            return
        }
        if ((!(enabled == "on" || enabled == "off")) || (!(cmd == "push" || cmd == "wkpush"))) {
            sendMessage("修改推送设置失败：指令不正确\n\n每日课程表推送开关\n用法 /setkcb push 学号 on/off\n\n" +
                    "周末无课程时课程表推送开关,\n用法 /setkcb wkpush 学号 on/off")
            return
        }

        if (CourseTimetableDBConn == null)
            CourseTimetableDBConn = DriverManager.getConnection("jdbc:sqlite:" + CourseTimetableConfig.DatabasePos)
        val statement = CourseTimetableDBConn!!.createStatement()

        val QQ = this.user!!.id
        val resultQQ = statement.executeQuery("SELECT 1 FROM bind WHERE sid = $sid and QQ = $QQ")
        if (!resultQQ.next()) {
            statement.close()
            sendMessage("修改设置失败，与账号 $sid 不存在绑定关系，请使用如下指令进行绑定 /bindkcb 学号 教务系统登录密码")
            return
        }

        val enableInt:Int = if (enabled == "on") 1 else 0
        val enableStr = if (enabled == "on") "启用" else "禁用"
        if (cmd == "push") {
            statement.executeUpdate("UPDATE bind SET pushMorning = $enableInt WHERE sid = $sid and QQ = $QQ")
            sendMessage("修改设置成功：已$enableStr 早间课表推送。")
        } else if (cmd == "wkpush") {
            statement.executeUpdate("UPDATE bind SET pushOnWeekend = $enableInt WHERE sid = $sid and QQ = $QQ")
            sendMessage("修改设置成功：已$enableStr 周末无课程是的课表推送。")
        }
        statement.close()
    }
}

object Command_mykcb : SimpleCommand(
    CourseTimetable, "mykcb", "获取完整课程表网页链接",
    description = "获取完整课程表网页链接, 用法 /mykcb"
) {
    @Handler
    suspend fun CommandSender.handle() {
        val num2circle = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
        val QQ = this.user!!.id
        if (CourseTimetableDBConn == null)
            CourseTimetableDBConn = DriverManager.getConnection("jdbc:sqlite:" + CourseTimetableConfig.DatabasePos)
        val statement = CourseTimetableDBConn!!.createStatement()

        val bindCountP = statement.executeQuery("SELECT count(*) FROM bind WHERE QQ = $QQ")
        var bindCount: Int? = null
        if (bindCountP.next())
            bindCount = bindCountP.getInt(1)
        if (bindCount == null || bindCount == 0) {
            statement.close()
            sendMessage("获取完整课程表失败：不存在绑定关系，请使用如下指令进行绑定 /bindkcb 学号 教务系统登录密码")
        }else if (bindCount == 1) {
            sendMessage("复制到浏览器打开体验更佳，QQ内置浏览器有几率显示不完全")
            val resultUrl = statement.executeQuery("SELECT courses.userID FROM bind JOIN courses ON bind.sid = courses.sid WHERE bind.QQ = $QQ ")
            val resultMsg = StringBuilder()
            if (resultUrl.next()) {
                resultMsg.append("https://kcb.brucec.cn/")
                resultMsg.append(resultUrl.getString(1))
                resultMsg.append(".html")
            }
            statement.close()
            delay(256)
            sendMessage(resultMsg.toString())
        } else if (bindCount > 1) {
            val resultUrl = statement.executeQuery("SELECT courses.sid, courses.userID FROM bind JOIN courses ON bind.sid = courses.sid WHERE bind.QQ = $QQ ")
            val resultMsg = StringBuilder()
            resultMsg.append("##### 完整课程表 #####\n")
            var msgCnt = 0
            while (resultUrl.next()) {
                resultMsg.append("\n")
                resultMsg.append(num2circle[msgCnt])
                resultMsg.append(resultUrl.getString(1))
                resultMsg.append("\n\n")
                resultMsg.append("https://kcb.brucec.cn/")
                resultMsg.append(resultUrl.getString(2))
                resultMsg.append(".html\n")
                msgCnt++
                if (msgCnt >= 20) msgCnt = 19
            }
            statement.close()
            resultMsg.append("\n复制到浏览器打开体验更佳，QQ内置浏览器有几率显示不完全。（此链接永久有效）")
            sendMessage(resultMsg.toString())
        }
    }
}


object CourseTimetableConfig : AutoSavePluginConfig("CourseTimetable") {
    val WebSocketPort by value<Int>(52225)
    val DatabasePos by value<String>("../ClassSchedule.db")
}

data class BindResult(
    val QQ: String,
    val username: String,
    val status: Boolean,
    val reason: String?
)

class CourseWebSocketServer(port: Int) : WebSocketServer(InetSocketAddress(port)) {

    override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
        CourseTimetable.logger.info { "New connection: " + conn.remoteSocketAddress.address.hostAddress }
    }

    override fun onClose(conn: WebSocket, code: Int, reason: String, remote: Boolean) {
        CourseTimetable.logger.info { "Lost connection: $conn" }
    }

    @OptIn(DelicateCoroutinesApi::class)
    override fun onMessage(conn: WebSocket, message: String) {
        if (message == "ping") conn.send("pong")
        CourseTimetable.logger.info { "Websocket $conn: $message" }
        GlobalScope.launch{
            try {
                val bindResult = gson.fromJson(message, BindResult::class.java)
                val QQ = bindResult.QQ.toLong()
                val friend = Bot.getInstance(2895727556).getFriend(QQ) ?: return@launch
                val sid = bindResult.username
                if (bindResult.status) {
                    if (CourseTimetableDBConn == null)
                        CourseTimetableDBConn = DriverManager.getConnection("jdbc:sqlite:" + CourseTimetableConfig.DatabasePos)
                    val statement = CourseTimetableDBConn!!.createStatement()
                    val resultQQ = statement.executeQuery("SELECT 1 FROM bind WHERE sid = $sid and QQ = $QQ")
                    if (!resultQQ.next()) // 未绑定过，插入数据库
                        statement.executeUpdate("INSERT INTO bind (sid, QQ, pushMorning, pushNight, pushOnWeekend) VALUES ($sid, $QQ, 1, 0, 0)")
                    statement.close()
                    friend.sendMessage("绑定教务系统账号成功，已绑定$sid 。\n\n如果需要绑定其他账号或修改已绑定账号的密码，重新执行本命令即可(一个QQ可以绑定多个账号，一个账号也可以被多个QQ绑定)\n\n在密码有效时，每日凌晨会自动抓取最新课表。\n\n\n觉得好用可以推荐给朋友哦qwq")
                    delay(512)
                    friend.sendMessage(queryShortStr)
                } else {
                    if (bindResult.reason == null) {
                        friend.sendMessage("绑定教务系统账号$sid 失败，请稍后再试。")
                    } else {
                        if (bindResult.reason.isEmpty() || bindResult.reason.elementAt(0) == '[') {
                            friend.sendMessage("绑定教务系统账号$sid 失败，原因是: " + bindResult.reason)
                        } else {
                            friend.sendMessage("绑定教务系统账号$sid 失败，教务系统返回的错误信息是: " + bindResult.reason)
                        }
                    }
                }
            } catch (e : Exception) {
                CourseTimetable.logger.error(e)
            }
        }
    }

    override fun onMessage(conn: WebSocket, message: ByteBuffer) {
        CourseTimetable.logger.info { "Websocket $conn: $message" }
    }

    override fun onError(conn: WebSocket, ex: Exception) {
        ex.printStackTrace()
        CourseTimetable.logger.error(ex)
    }

    override fun onStart() {
        CourseTimetable.logger.info { "Websocket server started!" }
        connectionLostTimeout = 0
        connectionLostTimeout = 119
    }
}
