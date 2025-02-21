from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from django.shortcuts import render
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from applications.academic_information.models import Student
from applications.programme_curriculum.models import Course as Courses, CourseInstructor
from applications.academic_procedures.models import course_registration
from applications.globals.models import ExtraInfo
from rest_framework.permissions import IsAuthenticated
from applications.online_cms.models import  Student_grades
from .serializers import StudentGradesSerializer
from datetime import datetime
from rest_framework import status
from .serializers import *
# from applications.online_cms
import pandas as pd
from rest_framework.parsers import MultiPartParser
from rest_framework.decorators import api_view, parser_classes
from django.http import JsonResponse
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

from applications.online_cms.models import Attendance

@api_view(['POST'])
@parser_classes([MultiPartParser])
def upload_attendance(request):
    if 'file' not in request.FILES:
        return Response({
            'error': 'No file was uploaded',
            'required_columns': ['student_id', 'instructor_id', 'date', 'present', 'no_of_attendance']
        }, status=status.HTTP_400_BAD_REQUEST)

    file = request.FILES['file']
    
    if not file.name.endswith(('.xls', '.xlsx')):
        return Response({
            'error': 'Invalid file format. Please upload an Excel file (.xls or .xlsx)'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        df = pd.read_excel(file)
        
        required_columns = ['student_id', 'instructor_id', 'date', 'present', 'no_of_attendance']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return Response({
                'error': 'Missing required columns',
                'missing_columns': missing_columns
            }, status=status.HTTP_400_BAD_REQUEST)

        successful_records = []
        errors = []
        
        # Validate all records
        for index, row in df.iterrows():
            try:
                # Validate date
                try:
                    attendance_date = pd.to_datetime(row['date']).date()
                except Exception as e:
                    errors.append({
                        'row': index + 2,
                        'error': f'Invalid date format: {row["date"]}'
                    })
                    continue

                # Validate student
                try:
                    student = Student.objects.filter(id=str(row['student_id'])).first()
                    if not student:
                        errors.append({
                            'row': index + 2,
                            'error': f'Student with ID {row["student_id"]} does not exist'
                        })
                        continue
                except Exception as e:
                    errors.append({
                        'row': index + 2,
                        'error': f'Invalid student ID: {str(e)}'
                    })
                    continue

                # Validate instructor
                try:
                    instructor = CourseInstructor.objects.filter(pk=int(row['instructor_id'])).first()
                    if not instructor:
                        errors.append({
                            'row': index + 2,
                            'error': f'Instructor with ID {row["instructor_id"]} does not exist'
                        })
                        continue
                except Exception as e:
                    errors.append({
                        'row': index + 2,
                        'error': f'Invalid instructor ID: {str(e)}'
                    })
                    continue

                # Validate attendance values
                try:
                    present = int(row['present'])
                    no_of_attendance = int(row['no_of_attendance'])
                    
                    if not (0 <= present <= no_of_attendance):
                        errors.append({
                            'row': index + 2,
                            'error': 'Present value cannot be greater than no_of_attendance'
                        })
                        continue
                except ValueError:
                    errors.append({
                        'row': index + 2,
                        'error': 'Invalid present or no_of_attendance value'
                    })
                    continue

                successful_records.append({
                    'student': student,
                    'instructor': instructor,
                    'date': attendance_date,
                    'present': present,
                    'no_of_attendance': no_of_attendance,
                    'row': index + 2
                })

            except Exception as e:
                errors.append({
                    'row': index + 2,
                    'error': str(e)
                })

        # Create/update records for valid data
        if successful_records:
            try:
                with transaction.atomic():
                    for record in successful_records:
                        attendance, created = Attendance.objects.update_or_create(
                            student_id=record['student'],
                            instructor_id=record['instructor'],
                            date=record['date'],
                            defaults={
                                'present': record['present'],
                                'no_of_attendance': record['no_of_attendance']
                            }
                        )
            except Exception as e:
                errors.append({
                    'error': f'Database error: {str(e)}'
                })
                successful_records = []

        response_data = {
            'message': 'Attendance upload completed',
            'total_records': len(df),
            'successful_records': len(successful_records),
            'failed_records': len(errors),
            'successful_details': [
                {
                    'row': record['row'],
                    'student_id': record['student'].id,
                    'date': record['date']
                } for record in successful_records
            ]
        }

        if errors:
            response_data['errors'] = errors
            return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
        
        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': f'Error processing file: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['GET'])
def view_attendance(request):
    """Endpoint to view all attendance records."""
    attendance_records = Attendance.objects.all()
    serializer = AttendanceSerializer(attendance_records, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['POST'])
def add_module(request):
    # Extract data from the request
    course_id = request.data.get('course_id')
    module_name = request.data.get('module_name')

    # Ensure the course exists
    try:
        course = Courses.objects.get(id=course_id)
    except Courses.DoesNotExist:
        return Response({"error": "Course not found"}, status=status.HTTP_404_NOT_FOUND)

    # Create the module
    module = Modules.objects.create(module_name=module_name, course=course)

    # Serialize the module data and return
    serializer = ModuleSerializer(module)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@api_view(['DELETE'])
def delete_module(request, module_id):
    try:
        # Get the module by primary key
        module = Modules.objects.get(pk=module_id)
        module.delete()  # Delete the module
        return Response(status=status.HTTP_204_NO_CONTENT)  # No content after deletion
    except Modules.DoesNotExist:
        return Response({"error": "Module not found"}, status=status.HTTP_404_NOT_FOUND)

# Add a slide
@api_view(['POST'])
def add_slide(request, module_id):
    try:
        # Get the module using module_id from the URL
        module = Modules.objects.get(id=module_id)
    except Modules.DoesNotExist:
        return Response({"error": "Module not found"}, status=status.HTTP_404_NOT_FOUND)

    # Extract data from the request body
    document_name = request.data.get('document_name')
    document_url = request.data.get('document_url')
    description = request.data.get('description', '')  # Default to an empty string if no description is provided

    # Create a new CourseDocument for the slide
    course_document = CourseDocuments.objects.create(
        course_id=module.course,
        module_id=module,
        document_name=document_name,
        document_url=document_url,
        description=description
    )

    # Serialize the document data and return the response
    serializer = CourseDocumentsSerializer(course_document)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

# Delete a slide
@api_view(['DELETE'])
def delete_slide(request, slide_id):
    try:
        # Get the slide by primary key
        slide = CourseDocuments.objects.get(pk=slide_id)
        slide.delete()  # Delete the slide
        return Response(status=status.HTTP_204_NO_CONTENT)  # No content after deletion
    except CourseDocuments.DoesNotExist:
        return Response({"error": "Slide not found"}, status=status.HTTP_404_NOT_FOUND)
        
from applications.academic_information.models import Student
from applications.programme_curriculum.models import Course as Courses, CourseInstructor
from applications.academic_procedures.models import course_registration
from applications.globals.models import ExtraInfo
from rest_framework.permissions import IsAuthenticated
from applications.online_cms.models import  Student_grades
from .serializers import StudentGradesSerializer
import datetime
from rest_framework.parsers import MultiPartParser

@api_view(['GET'])
def courseview(request):
    user = request.user
    extrainfo = ExtraInfo.objects.select_related().get(user=user)
    
    if extrainfo.user_type == 'student':
        student = Student.objects.select_related('id').get(id=extrainfo)
        register = course_registration.objects.select_related().filter(student_id=student)
        
        courses_info = [Courses.objects.select_related().get(pk=reg.course_id.id) for reg in register]
        course_serializer = CourseRegistrationSerializer(courses_info, many=True)
        
        data = {"courses": course_serializer.data}
        return Response(data, status=status.HTTP_200_OK)
        
    elif extrainfo.user_type == 'faculty':
        instructor = CourseInstructor.objects.select_related('course_id').filter(instructor_id=extrainfo)
        courses_info = [Courses.objects.select_related().get(pk=ins.course_id.id) for ins in instructor]
        
        course_serializer = CourseRegistrationSerializer(courses_info, many=True)
        data = {"courses": course_serializer.data}
        return Response(data, status=status.HTTP_200_OK)
    
    else:
        return Response({"error": "error occurred"})


@api_view(['GET'])
@permission_classes([AllowAny])
def course(request):
    user = request.user
    course_code = request.GET.get('course_code')
    version = request.GET.get('version')
    extrainfo = ExtraInfo.objects.select_related().get(user=user)
    
    if extrainfo.user_type == 'student':
        student = Student.objects.select_related('id').get(id=extrainfo)
        course = Courses.objects.select_related().get(code=course_code, version=version)
        instructor = CourseInstructor.objects.select_related().get(course_id=course, batch_id=student.batch_id)

        course_serializer = CoursesSerializer(course)
        instructor_serializer = CourseInstructorSerializer(instructor)

        modules = Modules.objects.select_related().filter(course_id=course)
        slides = CourseDocuments.objects.select_related().filter(course_id=course)
        
        modules_with_slides = {
            m: [slide for slide in slides if slide.module_id.id == m.id] or 0 
            for m in modules
        }
        
        attendance_records = Attendance.objects.select_related().filter(student_id=student, instructor_id=instructor)
        total_attendance = len(attendance_records)
        count = sum(1 for record in attendance_records if record.present)
        present_attendance = {record.date: int(record.present) for record in attendance_records}
        attendance_percent = round((count / total_attendance) * 100, 2) if total_attendance else 0
        
        attendance_file = AttendanceFiles.objects.select_related().filter(course_id=course)
        
        comments = Forum.objects.select_related().filter(course_id=course).order_by('comment_time')
        answers = {
            comment: ForumReply.objects.select_related().filter(forum_ques=comment)
            for comment in comments
        }
        
        data = {
            'course': course_serializer.data,
            'instructor': instructor_serializer.data,
            'modules': ModulesSerializer(modules, many=True).data,
            'slides': CourseDocumentsSerializer(slides, many=True).data,
            'attendance': AttendanceSerializer(attendance_records, many=True).data,
            'present_attendance': present_attendance,
            'attendance_percent': attendance_percent,
            'attendance_file': AttendanceFilesSerializer(attendance_file, many=True).data,
        }
        
        return Response(data, status=status.HTTP_200_OK)
    
    else:
        instructor = CourseInstructor.objects.select_related('course_id').filter(instructor_id=extrainfo)
        
        for ins in instructor:
            if ins.course_id.code == course_code and ins.course_id.version == Decimal(version):
                registered_students = course_registration.objects.select_related('student_id').filter(course_id=ins.course_id)
                students_info = [Student.objects.select_related().get(pk=stu.student_id.id) for stu in registered_students]
                
                topics = Topics.objects.select_related().filter(course_id=ins.course_id)
                attendance_records = {
                    x.student_id.id.id: {
                        'count': sum(1 for a in Attendance.objects.select_related().filter(student_id=x.student_id, instructor_id=ins) if a.present),
                        'attendance_percent': round(
                            (sum(1 for a in Attendance.objects.select_related().filter(student_id=x.student_id, instructor_id=ins) if a.present)
                             / len(Attendance.objects.select_related().filter(student_id=x.student_id, instructor_id=ins))) * 100,
                            2
                        ) if len(Attendance.objects.select_related().filter(student_id=x.student_id, instructor_id=ins)) else 0
                    }
                    for x in registered_students
                }

                modules = Modules.objects.select_related().filter(course_id=ins.course_id)
                slides = CourseDocuments.objects.select_related().filter(course_id=ins.course_id)

                gradingscheme = GradingScheme.objects.select_related().filter(course_id=ins.course_id)
                topics_serializer = TopicsSerializer(topics, many=True)
                
                data = {
                    "students": StudentSerializer(students_info, many=True).data,
                    "topics": topics_serializer.data,
                    "present_att": attendance_records,
                    "modules": ModulesSerializer(modules, many=True).data,
                    "slides": CourseDocumentsSerializer(slides, many=True).data,
                    "grading_scheme": GradingSchemeSerializer(gradingscheme, many=True).data,
                }
                
                return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
def view_attendance(request, course_code, version):
    user = request.user

    if not course_code or not version:
        return Response({"error": "course_code and version are required parameters"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        extrainfo = ExtraInfo.objects.select_related().get(user=user)
    except ExtraInfo.DoesNotExist:
        return Response({"error": "User information not found"}, status=status.HTTP_404_NOT_FOUND)

    if extrainfo.user_type == 'student':
        try:
            student = Student.objects.select_related('id').get(id=extrainfo)
            course = Courses.objects.select_related().get(code=course_code, version=version)
            instructor = CourseInstructor.objects.select_related().get(course_id=course, batch_id=student.batch_id)
            print(instructor)
            print(student)
            print(course)
        except (Student.DoesNotExist, Courses.DoesNotExist, CourseInstructor.DoesNotExist):
            return Response({"error": "Course or instructor not found"}, status=status.HTTP_404_NOT_FOUND)

        attendance_records = Attendance.objects.select_related().filter(student_id=student, instructor_id=instructor)
        attendance_serializer = AttendanceSerializer(attendance_records, many=True)

        return Response(attendance_serializer.data, status=status.HTTP_200_OK)

    elif extrainfo.user_type == 'instructor':
        try:
            instructor = CourseInstructor.objects.select_related('course_id').get(instructor_id=extrainfo, course_id__code=course_code, course_id__version=version)
        except CourseInstructor.DoesNotExist:
            return Response({"error": "Instructor or course not found"}, status=status.HTTP_404_NOT_FOUND)

        registered_students = course_registration.objects.select_related('student_id').filter(course_id=instructor.course_id)
        attendance_records = Attendance.objects.select_related().filter(instructor_id=instructor, student_id__in=[stu.student_id for stu in registered_students])
        attendance_serializer = AttendanceSerializer(attendance_records, many=True)

        return Response(attendance_serializer.data, status=status.HTTP_200_OK)

    return Response({"error": "Invalid user type"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def submit_marks(request, course_code, version):
    user = request.user
    extrainfo = ExtraInfo.objects.select_related().get(user=user)
    course_id = Courses.objects.select_related().get(code=course_code, version=version)
    
    if extrainfo.user_type == 'faculty':
        form_data = request.data.copy()
        year = datetime.datetime.now().year
        
        for i in range(int(len(form_data.getlist('stu_marks'))/3)):
            student = Student.objects.select_related().get(id=str(form_data.getlist('stu_marks')[(i*3)]))
            batch = str(student.batch)
            already_existing_data = Student_grades.objects.filter(roll_no=str(form_data.getlist('stu_marks')[(i*3)]))
            
            data = {
                'semester': student.curr_semester_no,
                'year': year,
                'roll_no': str(form_data.getlist('stu_marks')[(i*3)]),
                'total_marks': form_data.getlist('stu_marks')[(i*3+1)],
                'grade': str(form_data.getlist('stu_marks')[(i*3+2)]),
                'batch': batch,
                'course_id': course_id.id,
            }
            
            if already_existing_data.exists():
                already_existing_data.update(**data)
            else:
                serializer = StudentGradesSerializer(data=data)
                if serializer.is_valid():
                    serializer.save()
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({"message": "Upload successful."}, status=status.HTTP_200_OK)
    return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)