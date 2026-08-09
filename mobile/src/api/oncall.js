import { request } from './request.js'

export function getCurrentOncall() {
  return request({ url: '/api/sre/oncall/current' })
}

export function listOncall() {
  return request({ url: '/api/sre/oncall' })
}

export function listOncallMembers() {
  return request({ url: '/api/sre/oncall/members' })
}

export function getMySchedule(username) {
  return new Promise((resolve, reject) => {
    request({ url: '/api/sre/oncall' })
      .then((data) => {
        const list = Array.isArray(data) ? data : []
        const mine = list.filter((r) => {
          if (!r || !r.members) return false
          const members = Array.isArray(r.members) ? r.members : []
          return members.indexOf(username) >= 0 || r.current_oncall === username
        })
        resolve({ items: mine, all: list })
      })
      .catch(reject)
  })
}

export function handover(id, toName) {
  return request({ url: `/api/sre/oncall/${id}/handover?to_name=${encodeURIComponent(toName)}`, method: 'POST' })
}

export function autoRotate(id) {
  return request({ url: `/api/sre/oncall/${id}/auto-rotate`, method: 'POST' })
}

export default {
  getCurrentOncall,
  listOncall,
  listOncallMembers,
  getMySchedule,
  handover,
  autoRotate,
}
