# -*- coding: utf-8 -*-
from copy import deepcopy
from inspect import getmro
from typing import Callable, Type, Union
from types import FunctionType

from pydantic import BaseModel, ValidationError
from sanic.exceptions import InvalidUsage, ServerError, SanicException
from sanic.log import error_logger
from sanic.request import Request


class ParsedArgsObj(dict):
    def __getattr__(self, item):
        return self.get(item)

    def __setattr__(self, key, value):
        self.update({key: value})

    def __deepcopy__(self, memo=None):
        return ParsedArgsObj(deepcopy(dict(self), memo=memo))


class DanticModelObj:
    def __init__(
            self,
            header: Type[BaseModel] = None,
            query: Type[BaseModel] = None,
            path: Type[BaseModel] = None,
            body: Type[BaseModel] = None,
            form: Type[BaseModel] = None,
            all: Type[BaseModel] = None,
            error: Union[Type[SanicException], Callable[[ValidationError], None], bool] = None,
    ) -> None:
        """
        The param must be a BaseModel class or must inherit from BaseModel \n
        if listed, the same model name's model will use strict mode
        """

        try:
            if body and form:
                raise AssertionError(
                    "sanic-dantic: " +
                    "body and form cannot be used at the same time."
                )

            self.items = {
                "header": header,
                "path": path,
                "query": query,
                "form": form,
                "body": body,
                "all": all,
                "error": error
            }

            for model in [header, path, query, form, body, all]:
                if model and BaseModel not in getmro(model):
                    raise AssertionError(
                        "sanic-dantic: " +
                        "model must inherited from Pydantic.BaseModel"
                    )

            if error and SanicException not in getmro(error):
                raise AssertionError(
                    "sanic-dantic: " +
                    "error must inherited from SanicException"
                )

        except AssertionError as e:
            error_logger.error(e)
            raise ServerError(str(e))

    def __repr__(self):
        return str(self.items)


def validate(
        request: Request,
        header: Type[BaseModel] = None,
        query: Type[BaseModel] = None,
        path: Type[BaseModel] = None,
        body: Type[BaseModel] = None,
        form: Type[BaseModel] = None,
        all: Type[BaseModel] = None,
        error: Union[Type[SanicException], Callable[[ValidationError], None], bool] = None
) -> ParsedArgsObj:
    """
    When there are the same parameter name in the model,
    the parameter in ParsedArgsObj will be overwritten,
    The priorities is: body = form > query > path > header
    """

    try:
        parsed_args = ParsedArgsObj()
        if header:
            parsed_args.update(header(**request.headers).dict())

        if path:
            parsed_args.update(path(**request.match_info).dict())

        if query:
            params = {
                key: val[0]
                if len(val) == 1 else val for key, val in request.args.items()
            }
            parsed_args.update(query(**params).dict())

        if form:
            form_data = {
                key: val[0]
                if len(val) == 1 else val
                for key, val in request.form.items()
            }
            parsed_args.update(form(**form_data).dict())

        elif body:
            parsed_args.update(body(**request.json).dict())


        if all:
            query_params = {
                key: val[0]
                if len(val) == 1 else val for key, val in request.args.items()
            }
            body_params = {}
            try:
                body_params = request.json
                if not isinstance(body_params, dict):
                    body_params = {}
            except:
                body_params = {
                    key: val[0]
                    if len(val) == 1 else val
                    for key, val in request.form.items()
                }


            params = {}
            params.update(request.headers)
            params.update(request.match_info)
            params.update(query_params)
            params.update(body_params)

            parsed_args.update(all(**params).dict())

    except ValidationError as e:
        # error handler function of sanic_dantic  >  default InvalidUsage
        if error:
            if error == True:
                raise e
            elif isinstance(error, FunctionType):
                error(e)

            error_msg = e.errors()[0]
            message = f'{error_msg.get("loc")[0]} {error_msg.get("msg")}'
            raise error(message)
        else:
            error_msg = e.errors()[0]
            message = f'{error_msg.get("loc")[0]} {error_msg.get("msg")}'
            error_logger.error(message)
            raise InvalidUsage(message)
    except Exception as e:
        raise e
    request.ctx.params = parsed_args
    return parsed_args