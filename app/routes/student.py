from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from typing import Dict
from fastapi import APIRouter, BackgroundTasks,Body, HTTPException
from bson import ObjectId
from pydantic import BaseModel, EmailStr
from .auth import get_password_hash,verify_password,create_reset_token,verify_reset_token
from models.StudentModel import Student,ProfileUpdate,PasswordChange,AttendanceRecord
from db.database import student
from db import database
from datetime import datetime
router = APIRouter()



attendance_collections = {
        'E1': database.E1,
        'E2': database.E2, 
        'E3': database.E3,
        'E4': database.E4,
    }

timetable_collections = {
        'E1': database.E1_timetable,
        'E2': database.E2_timetable, 
        'E3': database.E3_timetable,
        'E4': database.E4_timetable,
    }

# student dashboard Route
@router.get("/dashboard")
async def get_student_dashboard(id_number: str, date: str):
    details = await student.find_one({'id_number': id_number})
    if not details:
        raise HTTPException(status_code=404, detail="Student not found")
    
    attendance_collection = attendance_collections[details['year']]
    attendance_report = await attendance_collection.find_one({'id_number': id_number})
    if not attendance_report:
        raise HTTPException(status_code=404, detail="Attendance report not found for your Student id")
    date_object = datetime.strptime(date, '%Y-%m-%d')
    current_date = datetime.now()
    current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
    weekday_name = date_object.strftime('%A').lower()
    
    timetable_collection = timetable_collections[details['year']]
    timetable = await timetable_collection.find_one()
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")
    section = details['section']
    
    if weekday_name not in timetable or section not in timetable[weekday_name]:
        raise HTTPException(status_code=404, detail="Timetable not found")
    
    daily_timetable = timetable[weekday_name][section]
    response = {}

    for subject, periods in daily_timetable.items():
        subject = subject.upper()
        subject_status = [periods]
        subject_data = attendance_report.get('attendance_report', {}).get(subject)
        if subject_data:
            for record in subject_data.get('attendance', []):
                if record['date'] == date:
                    subject_status.append(len(periods))
                    subject_status.append(record['status'])
                    break
            else:
                if date_object < current_date:
                    subject_status.append(len(periods))
                    subject_status.append('Cancelled')
                else:
                    subject_status.append(len(periods))
                    subject_status.append('Upcoming')
        else:
            if date_object < current_date:
                subject_status.append(len(periods))
                subject_status.append('Cancelled')
            else:
                subject_status.append(len(periods))
                subject_status.append('Upcoming')
        response[subject] = subject_status

    return {"Student_id":id_number, "name":details['first_name']+' '+details['last_name'] , "Timetable":response}


        

# View Profile
@router.get("/students/{id_number}/profile/")
async def view_profile(id_number: str):
    details = await student.find_one({"id_number": id_number})
    if not details:
        raise HTTPException(status_code=404, detail="Student not found")
    details["_id"] = str(details["_id"])  
    return {"Student details":details}

# Change Password
@router.put("/students/{id_number}/change-password/")
async def change_password(id_number: str, data: PasswordChange):
    details = await student.find_one({"id_number": id_number})
    print(details)
    if not details:
        raise HTTPException(status_code=404, detail="Student not found")
    response = verify_password(data.current_password,details['password'])
    print(response)
    if response:
        result = await student.update_one({"id_number": id_number}, {"$set": {"password": get_password_hash(data.new_password)}})
        if result.modified_count > 0:
            return {"message": "Password changed successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to update password. Please try again.")
    else:
        raise HTTPException(status_code=400, detail="Incorrect password. Please try again.")


# View Attendance Summary
@router.get("/attendance")
async def view_attendance_summary(id_number: str , year : str):
    if id_number:
        prefix = attendance_collections[year]
        if prefix is not None:
            attendance_report = await prefix.find_one({"id_number": id_number}) 
        else:
            attendance_report = None
        if  attendance_report:
            attendance_summary = calculate_percentage(attendance_report)
            return { "attendance_report": attendance_report["attendance_report"] ,
                "attendance_summary" : attendance_summary
            
            }
        else:
            raise HTTPException(status_code=404, detail="Student details or attendance details are not found")




def calculate_percentage(attendance_report):
    result = {}
    total_classes = 0
    total_present = 0

    for subject, data in attendance_report['attendance_report'].items():
        num_classes = len(data['attendance'])
        
        num_present = 0
        for entry in data['attendance']: 
            if entry['status'] == 'present':
                num_present+=1
        
        percentage = (num_present / num_classes) * 100 if num_classes > 0 else 0

        result[subject] = {
            'faculty_name': data['faculty_name'],
            'num_classes': num_classes,
            'num_present': num_present,
            'percentage': percentage
        }

        total_classes += num_classes
        total_present += num_present

    total_percentage = (total_present / total_classes) * 100 if total_classes > 0 else 0
    
    result['total'] = {
        'total_classes': total_classes,
        'total_present': total_present,
        'total_percentage': total_percentage
    }

    return result


def get_attendance_collection(string: str):
    return attendance_collections[string]

def get_titmtable_collections(string: str):
    return timetable_collections[string]

# # Email Sending Function
# @router.post("/sendEmail")
# async def send_email():
   
#     sender_email = "chincholivinitha195@gmail.com"
#     sender_password = "Vinitha@321"

    
#     # Establish connection to the SMTP server
#     with smtplib.SMTP("smtp.gmail.com", 587) as server:
#         server.starttls()  # Upgrade the connection to secure
#         server.login(sender_email, sender_password)  # Log in to your email
#         # Test sending an email
#         server.sendmail(sender_email, "chinvin9521@gmail.com", "Test email")

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password :str



def send_reset_email(email: str, reset_token: str):
    """Send the password reset email."""
    reset_link = f"http://localhost:8000/reset-password?token={reset_token}"
    subject = "Password Reset Request"
    body = f"Click the link to reset your password: {reset_link}\nThis link will expire in 1 hour."
    
    sender_email = "chincholivinitha195@gmail.com"
    sender_password = "vhwiyctnbtbynhkn"

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, email, msg.as_string())
        server.quit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

# Routes
@router.post("/forgot-password", response_model=Dict[str, str])
async def forgot_password(request: ForgotPasswordRequest):
    """Handle forgot password request."""
    student_data = student.find_one({"email": request.email})
    if not student_data:
        raise HTTPException(status_code=404, detail="Email not registered")

    reset_token = create_reset_token(request.email)
    print(reset_token)
    send_reset_email(request.email, reset_token)
    return {"message": "Password reset email sent"}



@router.post("/reset-password", response_model=Dict[str, str])
async def reset_password(request: ResetPasswordRequest):
    """Reset the password using the provided token."""
    # Check if new password and confirm password match
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # Verify the reset token and extract the email
    email = verify_reset_token(request.token)
    print(email)
    # Hash the new password
    hashed_password =get_password_hash(request.new_password)

    print(hashed_password)
    # # Update the password in MongoDB
    await student.update_one(
        {"email_address":email},
        {"$set": {"password": hashed_password}, "$unset": {"reset_token": ""}},
    )

    # # if result.matched_count == 0:
    # #     raise HTTPException(status_code=404, detail="Student not found")

    return {"message": "Password reset successful"}

# @router.post("/reset-password")
# async def reset_password(request: ResetPasswordRequest):
#     """Handle password reset requests."""
#     email = verify_reset_token(request.token)
#     if not email:
#         raise HTTPException(status_code=400, detail="Invalid or expired token")

#     student = await student.find_one({"email": email})
#     if not student:
#         raise HTTPException(status_code=404, detail="Student not found")

#     # Update the password and remove the token
#     hashed_password = get_password_hash(request.new_password)
#     await student.update_one(
#         {"_id": student["_id"]},
#         {"$set": {"hashed_password": hashed_password}, "$unset": {"reset_token": ""}},
#     )

#     return {"message": "Password reset successful"}