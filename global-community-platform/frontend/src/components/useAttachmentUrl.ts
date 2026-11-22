import { useEffect, useState } from 'react'
import { api } from '../services/api'

/**
 * Load an attachment through the authenticated API client and expose it as a blob URL,
 * so files from private communities get the same JWT check as every other request.
 */
export function useAttachmentUrl(attachmentId: number | null) {
  const [url, setUrl] = useState('')
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (attachmentId === null) return
    let active = true
    let objectUrl = ''
    setUrl('')
    setFailed(false)
    api.get(`/attachments/${attachmentId}/download/`, { responseType: 'blob' })
      .then((response) => {
        objectUrl = URL.createObjectURL(response.data)
        if (active) setUrl(objectUrl)
        else URL.revokeObjectURL(objectUrl)
      })
      .catch(() => { if (active) setFailed(true) })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [attachmentId])

  return { url, failed }
}
