const PLAYBACK_BUILD_CONTEXTS = IdDict{Task, Vector{Function}}()
const PLAYBACK_BUILD_CONTEXTS_LOCK = ReentrantLock()

"""Register a playback stop callback while an experiment page is being built."""
function register_playback_cancel!(cancel_callback::Function)
    lock(PLAYBACK_BUILD_CONTEXTS_LOCK) do
        callbacks = get(PLAYBACK_BUILD_CONTEXTS, current_task(), nothing)
        isnothing(callbacks) || push!(callbacks, cancel_callback)
    end
    return cancel_callback
end

function _remove_playback_build_context!(task::Task, callbacks::Vector{Function})
    lock(PLAYBACK_BUILD_CONTEXTS_LOCK) do
        if get(PLAYBACK_BUILD_CONTEXTS, task, nothing) === callbacks
            delete!(PLAYBACK_BUILD_CONTEXTS, task)
        end
    end
    return nothing
end

"""Build a page and stop every registered playback loop when its browser session leaves."""
function build_with_playback_lifecycle(session::Bonito.Session, builder::Function)
    task = current_task()
    callbacks = Function[]
    lock(PLAYBACK_BUILD_CONTEXTS_LOCK) do
        haskey(PLAYBACK_BUILD_CONTEXTS, task) && error("播放生命周期构建不可嵌套")
        PLAYBACK_BUILD_CONTEXTS[task] = callbacks
    end

    figure = try
        builder()
    finally
        _remove_playback_build_context!(task, callbacks)
    end

    cancel_all = () -> begin
        for callback in callbacks
            try
                callback()
            catch err
                @debug "停止实验播放任务失败" exception = (err, catch_backtrace())
            end
        end
        nothing
    end

    on(session, session.on_close) do closed
        closed && cancel_all()
    end

    cancellation_requested = Observable(false)
    on(session, cancellation_requested) do should_cancel
        should_cancel && cancel_all()
    end
    lifecycle_script = Bonito.DOM.script(js"""
    (() => {
        const cancelPlayback = () => $(cancellation_requested).notify(true);
        window.addEventListener("pagehide", cancelPlayback, {once: true});
        window.addEventListener("beforeunload", cancelPlayback, {once: true});
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "hidden") cancelPlayback();
        });
    })();
    """)
    return (; figure, lifecycle_script)
end
