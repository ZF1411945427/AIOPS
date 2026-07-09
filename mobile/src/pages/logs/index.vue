<template>
    <view class="page-wrap">
        <view class="empty-state">
            <text class="empty-icon">📋</text>
            <text class="empty-text">日志管理</text>
        </view>
    </view>
</template>

<script setup>
</script>

<style>
.page-wrap { min-height: 100vh; background: #f5f7fa; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding-top: 120px; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 14px; color: #999; }
</style>
