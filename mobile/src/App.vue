<script>
import { onLaunch, onShow, onHide } from '@dcloudio/uni-app'
import { useUserStore } from './store/user.js'

export default {
    setup() {
        onLaunch(() => {
            const userStore = useUserStore()
            userStore.checkLogin()
        })
        onShow(() => {
            const userStore = useUserStore()
            if (userStore.token) {
                userStore.checkBiometric()
            }
        })
        onHide(() => {})
    }
}
</script>

<style lang="scss">
page {
    background: $bg;
    color: $text;
    font-size: $font-md;
    font-family: -apple-system, 'PingFang SC', 'Helvetica Neue', Helvetica, 'Microsoft YaHei', sans-serif;
    -webkit-font-smoothing: antialiased;
}

view, text, image, scroll-view, button, input, textarea {
    box-sizing: border-box;
}

.page-wrap {
    min-height: 100vh;
    padding: 24rpx;
}

.card {
    background: $bg-card-solid;
    border-radius: $card-radius;
    padding: 32rpx;
    box-shadow: $card-shadow;
    margin-bottom: 24rpx;
}

.btn-primary {
    height: $btn-height;
    line-height: $btn-height;
    background: $primary;
    color: #fff;
    border-radius: $btn-radius;
    font-size: $font-lg;
    font-weight: 600;
    text-align: center;
    border: none;
}

.btn-primary::after {
    border: none;
}

.btn-primary[disabled] {
    background: $border;
    color: $text-muted;
}

.btn-ghost {
    height: $btn-height;
    line-height: $btn-height;
    background: transparent;
    color: $primary;
    border: 2rpx solid $primary;
    border-radius: $btn-radius;
    font-size: $font-lg;
    font-weight: 600;
    text-align: center;
}

.btn-ghost::after {
    border: none;
}

.input-field {
    height: $input-height;
    background: $bg-card-solid;
    border: 2rpx solid $border;
    border-radius: 16rpx;
    padding: 0 28rpx;
    font-size: $font-md;
    color: $text;
}

.input-field:focus {
    border-color: $primary;
}

.text-muted {
    color: $text-muted;
}

.text-secondary {
    color: $text-secondary;
}

.flex-row {
    display: flex;
    flex-direction: row;
    align-items: center;
}

.flex-col {
    display: flex;
    flex-direction: column;
}

.flex-between {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.divider {
    height: 2rpx;
    background: $border;
    margin: 24rpx 0;
}

.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 120rpx 0;
    color: $text-muted;
}

.empty-state .empty-icon {
    font-size: 80rpx;
    margin-bottom: 24rpx;
}

.empty-state .empty-text {
    font-size: $font-sm;
}
</style>
