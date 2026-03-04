import os
import time
import random

OTP_TTL_SECONDS = 300          # 5 mins
OTP_RESEND_COOLDOWN = 30       # 30 sec
OTP_MAX_ATTEMPTS = 3

def generate_otp():
    return str(random.randint(100000, 999999))

def can_resend(last_sent_time: float | None):
    if not last_sent_time:
        return True
    return (time.time() - last_sent_time) >= OTP_RESEND_COOLDOWN

def is_expired(sent_time: float | None):
    if not sent_time:
        return True
    return (time.time() - sent_time) > OTP_TTL_SECONDS


# ✅ TEMP: WhatsApp not enabled in MSG91 (template issue) - so fallback
def send_whatsapp_otp(mobile, otp):
    # later msg91 whatsapp api call here
    print(f"[TEMP] WhatsApp OTP to {mobile}: {otp}")
    return False  # now always False => fallback to SMS

def send_sms_otp(mobile, otp):
    # nee existing MSG91 SMS function ni ikada call cheyyi
    # Example:
    # msg91_send_sms(mobile, otp)
    print(f"[TEMP] SMS OTP to {mobile}: {otp}")
    return True