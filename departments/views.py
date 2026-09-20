from django.shortcuts import render, get_object_or_404

from .models import Department, STREAM_ORDER

# Как попасть на кафедру — общий для факультета порядок распределения,
# используется и на списке кафедр, и на странице конкретной кафедры.
DISTRIBUTION_STEPS = [
    {
        'title': 'Дождаться объявления о распределении на 2-м курсе',
        'note': 'До этого все студенты учатся по общей программе факультета.',
    },
    {
        'title': 'Изучить материалы кафедр',
        'note': 'Каждая кафедра публикует презентацию о направлениях, спецкурсах и семинарах.',
    },
    {
        'title': 'Выбрать кафедру одного из трёх потоков',
        'note': '20 кафедр разбиты на три лекционных потока; поток определяет набор общих спецкурсов.',
    },
    {
        'title': 'Подать заявление в учебный отдел',
        'note': 'Заявление с указанием кафедры подаётся в срок, объявленный деканатом.',
    },
    {
        'title': 'Выбрать семинар и научного руководителя',
        'note': 'После зачисления студент выбирает спецсеминар и руководителя курсовой работы.',
    },
]


def department_list(request):
    departments = Department.objects.all()
    groups = []
    for stream in STREAM_ORDER:
        items = [d for d in departments if d.stream == stream]
        if items:
            groups.append({'stream': stream, 'items': items})

    context = {
        'groups': groups,
        'distribution_steps': DISTRIBUTION_STEPS,
        'total_count': departments.count(),
    }
    return render(request, 'departments/list.html', context)


def department_detail(request, dept_id):
    department = get_object_or_404(Department, pk=dept_id)
    all_departments = Department.objects.all().order_by('name')

    distribution_steps = list(DISTRIBUTION_STEPS)
    if len(distribution_steps) > 2:
        distribution_steps[2] = {
            'title': f'Выбрать кафедру: {department.abbr} — {department.stream.lower()}',
            'note': distribution_steps[2]['note'],
        }

    context = {
        'department': department,
        'all_departments': all_departments,
        'distribution_steps': distribution_steps,
    }
    return render(request, 'departments/detail.html', context)
